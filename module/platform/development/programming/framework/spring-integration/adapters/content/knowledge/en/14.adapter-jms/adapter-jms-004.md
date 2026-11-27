# JMS inbound gateway request-reply

## 1. When do you need a JMS inbound gateway?

An ERP system sends an order status query to the JMS queue `orders.status.request` and expects a `PAID`, `PENDING`, or `NOT_FOUND` response on a JMS reply destination. The Spring Integration application must **receive the JMS request, execute business logic, and send a JMS reply** back to the right caller. The **JMS inbound gateway** provides the entry point for this two-way exchange.

In the **SPRING_INTEGRATION_ADAPTERS** module, inbound/outbound adapters connect one-way data flows, gateways handle request-reply, pollers trigger scheduled data sources, and `MessageChannel`s link processing steps independently of external protocols. This lesson dives into the **JMS inbound gateway request-reply** pattern; the characteristics of message contracts, errors, connections, and transactions also form the foundation when integrating files, SFTP, HTTP, AMQP, Kafka, or databases.

**After this lesson, you should be able to:**

1. Explain the path from a JMS request to a Spring Message and back to a JMS reply.
2. Configure a `Jms.inboundGateway` using Java DSL or XML.
3. Understand the roles of `JMSReplyTo`, `JMSCorrelationID`, and `JMSMessageID` so replies are never mixed up across concurrent requests.
4. Distinguish business responses from exceptions, timeouts, rollbacks, and redeliveries.
5. Verify the flow on a real broker and recognize the boundary between a JMS transaction and a database transaction.

### How does a gateway differ from a channel adapter?

| Endpoint | Receive/Send | Must return a JMS reply? | How it is triggered |
|---|---|---|---|
| JMS polling inbound channel adapter | Receive | No | `Poller` calls `JmsTemplate.receive()` on a schedule |
| JMS message-driven inbound channel adapter | Receive | No | JMS listener container receives the message |
| JMS outbound channel adapter | Send | No | Spring Message enters the JMS-sending handler |
| **JMS inbound gateway** | **Receive request and send reply** | **Yes** | Listener container receives JMS request, awaits processing result |
| JMS outbound gateway | Send request and receive reply | Yes | Spring Integration acts as the JMS caller from inside the app |

An inbound gateway fits when an **external JMS client** initiates the request and the current application acts as the responder. If the current application proactively calls another JMS service, use an **outbound gateway**.

## 2. Request-reply architecture and the two message layers

~~~mermaid
sequenceDiagram
    participant Client as ERP (JMS client)
    participant Broker as JMS Broker
    participant Gateway as JMS Inbound Gateway
    participant Flow as MessageChannel + Handler

    Client->>Broker: TextMessage request (JMSReplyTo, correlation)
    Broker->>Gateway: Delivers from orders.status.request
    Gateway->>Flow: Spring Message + replyChannel
    Flow-->>Gateway: Spring Message containing result
    Gateway->>Broker: JMS reply to JMSReplyTo
    Broker-->>Client: Reply matched to request
~~~

Distinguish clearly:

- **JMS message** is an object from the `jakarta.jms.Message` API, with a JMS body, JMS headers, and properties, traveling through the broker.
- **Spring Message** belongs to `org.springframework.messaging.Message<?>`, with payload and `MessageHeaders`; it travels inside the integration flow via `MessageChannel`.
- **Gateway** receives the JMS message, converts it into a Spring Message, dispatches the request downstream, and waits for a Spring reply. Then the gateway converts the Spring reply into a JMS message to send back to the corresponding destination.

Example request from ERP:

~~~json
{
  "requestId": "req-7001",
  "schemaVersion": 1,
  "operation": "getOrderStatus",
  "orderId": "ORD-700"
}
~~~

Example reply:

~~~json
{
  "requestId": "req-7001",
  "schemaVersion": 1,
  "resultCode": "OK",
  "orderId": "ORD-700",
  "status": "PAID"
}
~~~

`requestId` in JSON is a **business ID** agreed upon by both systems for tracing/idempotency. It is not automatically `JMSMessageID` or `JMSCorrelationID`; JMS headers belong to the **request-reply protocol** and must be checked independently.

### Detailed path

1. The producer sends a `TextMessage` to the `orders.status.request` queue and usually sets `JMSReplyTo` to a temporary queue or a client-managed reply queue.
2. The inbound gateway's JMS listener container receives the message and invokes the listener. The gateway applies the JMS converter/header mapper to create a Spring Message.
3. The Spring Message is sent to the request channel; the gateway provides a reply path (usually via a temporary `replyChannel` header).
4. A service activator, transformer, or subflow processes the request and **returns** an appropriate value/Message.
5. The reply reaches the gateway via the reply channel; the gateway converts the payload to a JMS message, selects the reply destination, and sends it.
6. The client receives the reply on the declared destination, then checks correlation to match it with the original request.

The inbound gateway uses a listener container and **does not require `PollerMetadata`**. With a `DirectChannel` and synchronous handler, the processing path typically runs on the listener thread, so slow requests can hold a consumer for a significant time.

## 3. Java DSL configuration from request queue to reply

The example uses **Spring Integration 6+** and **Jakarta JMS**. Older Spring Integration/Spring Framework versions may use the `javax.jms` package. To run the example, the project needs Spring Integration JMS along with the JMS client matching the broker (Artemis, IBM MQ, or another provider).

~~~xml
<!-- Dependency versions managed by Spring Boot BOM. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Add starter/client for the JMS provider and configure the broker accordingly. -->
~~~

Prerequisites are a working `ConnectionFactory` bean and the `orders.status.request` queue either already created or allowed to auto-create under broker policy. Do not assume default connection settings.

### 3.1. Creating the gateway and handler

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class OrderStatusJmsGatewayConfiguration {

    @Bean
    public IntegrationFlow orderStatusJmsGateway(
            ConnectionFactory connectionFactory,
            OrderStatusService orderStatusService) {

        return IntegrationFlow
                .from(Jms.inboundGateway(connectionFactory)
                        .requestDestination("orders.status.request"))
                .handle(String.class, (requestJson, headers) ->
                        orderStatusService.getStatusAsJson(requestJson))
                .get();
    }
}
~~~

A service for the learner to implement:

~~~java
public interface OrderStatusService {
    // Return JSON with requestId/resultCode/status; throw exception on infrastructure failure.
    String getStatusAsJson(String requestJson);
}
~~~

Meaning of each step:

- `Jms.inboundGateway(connectionFactory)` creates a message-driven JMS inbound gateway using a listener container to receive requests.
- `.requestDestination("orders.status.request")` selects the request-receiving queue. The value must match the producer's destination.
- `.handle(String.class, ...)` accepts only Spring Messages whose payload after conversion is `String`. When the client sends a JMS `TextMessage`, the common default converter produces a `String`.
- The handler **returns a JSON string** instead of `null`: Spring Integration uses the return value as the reply message for the gateway to send a JMS reply.
- `.get()` completes the `IntegrationFlow`. In this example, the gateway uses the flow's internal reply channel mechanism; there is no need to write a separate outbound JMS adapter to send the response.

If the service throws an error, the flow does not produce a normal reply; whether the error becomes a response or triggers a rollback depends on the configured error channel/transaction. If the handler returns `null` or no consumer produces a reply, the caller may time out and the gateway may also report a timeout depending on configuration.

### 3.2. Test JMS client using `JmsTemplate.sendAndReceive`

The following illustration uses a Spring JMS client in a test environment. `JmsTemplate.sendAndReceive` automatically creates a temporary queue for the reply and attaches it to the request's `JMSReplyTo` header.

~~~java
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;

public String requestOrderStatus(JmsTemplate jmsTemplate)
        throws jakarta.jms.JMSException {

    // Configured on the client's JmsTemplate instance, not the inbound gateway.
    jmsTemplate.setReceiveTimeout(5000);

    Message reply = jmsTemplate.sendAndReceive(
            "orders.status.request",
            session -> {
                TextMessage request = session.createTextMessage(
                        "{\"requestId\":\"req-7001\",\"schemaVersion\":1,"
                        + "\"operation\":\"getOrderStatus\",\"orderId\":\"ORD-700\"}");
                request.setStringProperty("clientName", "erp-service");
                return request;
            });

    if (reply == null) {
        throw new IllegalStateException("JMS request timed out waiting for reply");
    }
    if (!(reply instanceof TextMessage)) {
        throw new IllegalStateException("Reply is not a JMS TextMessage");
    }
    return ((TextMessage) reply).getText();
}
~~~

This is a method excerpt for use in a service/test that already has a provider-configured `JmsTemplate`; it is not a complete application. The sending/receiving client may run in a different process from the server. If the broker does not support temporary destinations or ACLs forbid creating them, you must use an appropriate reply queue and a client-side correlation mechanism.

**Distinguishing two timeouts:** `jmsTemplate.setReceiveTimeout(5000)` on the **client** limits how long to wait for a JMS reply (in milliseconds). It **does not** automatically configure the gateway timeout on the server, nor does it guarantee the handler finishes within 5 seconds.

### 3.3. Equivalent XML namespace

~~~xml
<int:channel id="orderStatusRequests"/>

<int-jms:inbound-gateway
        id="orderStatusJmsGateway"
        connection-factory="jmsConnectionFactory"
        request-destination-name="orders.status.request"
        request-channel="orderStatusRequests"/>

<int:service-activator
        input-channel="orderStatusRequests"
        ref="orderStatusService"
        method="getStatusAsJson"/>
~~~

This is an XML **fragment**. The application also needs the `int`/`int-jms` namespace declarations, the `jmsConnectionFactory` bean, and `orderStatusService`. The `getStatusAsJson(String)` method must return a valid value. In this configuration, Spring Integration preserves reply channel information when sending the request to the handler; the handler does not need to know the JMS reply queue name.

## 4. `JMSReplyTo` and the correlation mechanism

A proper request-reply flow must respond to the **right place** and match the reply to the **right request**, especially when multiple clients or multiple concurrent requests are sent.

### 4.1. Selecting the reply destination

Upon receiving a request, the JMS inbound gateway prioritizes the `JMSReplyTo` header to choose where to send the reply. If this header is absent, you can configure a fallback destination with `defaultReplyDestination`, `defaultReplyQueueName`, or `defaultReplyTopicName`.

Java DSL example when a legacy ERP does not set `JMSReplyTo`:

~~~java
// Replace only the endpoint configuration part in the IntegrationFlow from section 3.
Jms.inboundGateway(connectionFactory)
        .requestDestination("orders.status.request")
        .defaultReplyQueueName("orders.status.reply")
~~~

Only configure a default queue when the **client actually knows about and is listening on** that queue. If multiple clients use a shared reply queue, clients must filter replies by correlation; otherwise, one client may read replies meant for another client.

| Reply destination strategy | Advantages | Trade-offs |
|---|---|---|
| `JMSReplyTo` as a temporary queue | Client gets replies on a queue scoped to its session; simple for short request-reply | Depends on permission to create temporary queues and connection lifecycle |
| `JMSReplyTo` as a static reply queue | Easy to observe; integrates with legacy apps | Requires selectors/correlation and safeguards against mis-consumption |
| `defaultReplyQueueName` on inbound gateway | Supports clients that omit `JMSReplyTo` | Must agree on reply queue contract and consumer upfront |
| `replyToExpression` (since Spring Integration 6.1) | Can derive fallback destination from the JMS request when `JMSReplyTo` is empty | Must restrict allowed target destinations, enforce ACLs, and validate data |

**Never take a reply destination name directly from untrusted payload data** and allow arbitrary sends. If dynamic replies are needed, use an allowlist of valid queues and a destination resolver with explicit permissions.

### 4.2. Why is `JMSCorrelationID` needed?

With multiple concurrent requests, a shared reply queue can hold several messages:

~~~text
Request A: JMSMessageID=ID:A, JMSReplyTo=orders.status.reply
Request B: JMSMessageID=ID:B, JMSReplyTo=orders.status.reply

Reply for A: JMSCorrelationID=ID:A
Reply for B: JMSCorrelationID=ID:B
~~~

One common pattern is for the server to set the **reply's** `JMSCorrelationID` to the **request's** `JMSMessageID`. Another pattern uses an existing correlation ID on the request: if the client sends a client-managed `JMSCorrelationID`, the reply echoes that value according to the agreed correlation configuration. Spring Integration's inbound gateway supports the correlation patterns used by Spring Integration's outbound gateway or standard JMS clients.

In a system using a shared reply queue, the client should use a JMS message selector or an internal dispatch mechanism to pick only replies matching its requests. Do not send all replies into one queue, receive them in arrival order, and assume `request 1 ↔ reply 1`.

**Three IDs to distinguish:**

- `JMSMessageID`: assigned by the provider to **each JMS message**; may differ when a producer resends the same command.
- `JMSCorrelationID`: links a reply to a request or exchange sequence per contract.
- `requestId`: business ID in JSON, useful for logging, deduplication, and tracing across multiple systems.

Do not assume `requestId` automatically equals `JMSCorrelationID` without explicit mapping. Test compatibility with a real client.

## 5. Request and reply contract: payload and header conversion

The JMS inbound gateway has **two distinct payload-extraction settings**:

| Property | Applies to | Default | Typical result |
|---|---|---|---|
| `extractRequestPayload` | Incoming JMS request → Spring Message | `true` | `TextMessage` → `String` payload |
| `extractReplyPayload` | Spring reply → Outgoing JMS reply | `true` | Spring `String` payload → JMS `TextMessage` |

With `extractRequestPayload(false)`, the original JMS message can be kept as the Spring payload; this couples the handler to the JMS API and session lifecycle. With `extractReplyPayload(false)`, the entire Spring Message can be converted as the JMS body by the converter, which is usually unsuitable for external consumers that only understand JSON. Keep the defaults and define an explicit schema in most business flows.

| JMS message | Spring payload with `SimpleMessageConverter` | Usage |
|---|---|---|
| `TextMessage` | `String` | JSON/XML with schema/version |
| `BytesMessage` | `byte[]` | Binary format with a defined contract |
| `MapMessage` | Map of values | Watch JMS and provider type limits |
| `ObjectMessage` | Java `Serializable` | Discouraged due to class compatibility and deserialization risks |

`HeaderMapper` handles mapping a subset of JMS headers/properties to Spring headers and vice versa. Not every Spring header is valid as a JMS property; arbitrary value objects or invalid property names may not be preserved. Protocol-controlling JMS headers such as `JMSReplyTo` and `JMSCorrelationID` should be verified in integration tests.

A useful contract for a status-lookup service:

- Request contains `requestId`, `schemaVersion`, `operation`, and `orderId`; the server rejects unsupported versions or operations.
- Success reply contains matching `requestId`, `resultCode=OK`, `orderId`, `status`.
- Business-error reply contains `requestId`, `resultCode` as an agreed error code, and a `message` that does not leak internal details.
- Define maximum processing time, retry policy, and state when no reply arrives.

**Malformed input must be handled intentionally.** If JSON parsing fails before extracting `requestId`, a reply can still return `INVALID_REQUEST` with `requestId=null` when the contract permits; if returning a safe reply is not possible, let the exception follow the appropriate error/rollback mechanism.

## 6. Timeouts, synchronous channels, and asynchronous processing paths

Same word "timeout", different locations:

| Wait point | Waiting for what? | On expiration |
|---|---|---|
| JMS client `JmsTemplate.receiveTimeout` | JMS reply on the reply destination | May receive `null` or report timeout at client layer |
| Gateway `replyTimeout` | Reply from the Spring Integration flow, especially under async processing | No reply found within the allotted time; error handling depends on config |
| Gateway `requestTimeout` | Sending the Spring request into a potentially blocking channel, e.g., a full bounded `QueueChannel` | Fails to place request into the channel in time |
| DB/HTTP access timeout | Completion of a downstream service call | Service throws error; gateway decides error reply or rollback |
| JMS time-to-live | JMS request/reply validity on the broker | Expired messages may be dropped or handled per broker policy |

Do not rely on **default values** when the system has strict SLAs; set explicit timeouts for the client, gateway, and downstream dependencies. Client wait time must account for queuing, processing, sending the reply, and broker latency. For example, a client waiting only 2 seconds while DB timeout is 10 seconds can create a **late reply** even when the server eventually succeeds.

### Keeping processing synchronous for short requests

`DirectChannel` allows the handler to return a result on the listener thread. The gateway can receive the reply immediately once the handler finishes. This model suits fast lookups and makes exceptions and transactions easy to reason about, though each slow request ties up a thread/consumer.

### When using `ExecutorChannel` or `QueueChannel`

The gateway can send the Spring Message to a consumer on another thread and then **wait for the reply via the reply channel**. In that case:

1. The reply may arrive after the gateway's timeout expires.
2. Exceptions from an asynchronous handler do not necessarily propagate back through the listener like a synchronous call stack.
3. The listener's JMS transaction does not automatically wrap a DB transaction running on another thread.
4. Once the client times out, downstream work may still be running; if the client retries, duplicate processing is a risk.

For tasks taking several minutes, consider an asynchronous **command + acknowledgement + status query/event** pattern instead of holding a JMS request-reply open too long. A request-reply gateway does not turn a long-running task into an instant completion.

## 7. Transactions, acknowledgement, and redelivery

**A JMS inbound gateway typically uses a listener container with transacted sessions** by default in Spring Integration (since version 4.2), **unless an external container is supplied**, in which case you must manage its configuration yourself. Spring Integration recommends transacted acknowledgement with `DefaultMessageListenerContainer` to reduce message-loss risk. Actual behavior also depends on the JMS provider and container configuration.

On a synchronous processing path:

1. The listener receives a JMS request inside a JMS transaction.
2. The gateway passes it to the handler; the handler produces a Spring reply.
3. The gateway sends the reply to `JMSReplyTo` or the fallback destination.
4. When the callback succeeds and the transaction commits, the broker treats receiving the request and sending the reply as completed under that JMS transaction.
5. If an unhandled exception escapes to the listener, the JMS transaction can roll back; the broker decides redelivery/DLQ according to its configuration.

Within a single broker and local JMS transaction, receiving and sending the reply can belong to the same transaction. **Do not infer that DB updates also belong to the JMS transaction.** If the handler commits to the DB and then sending the reply fails or the listener rolls back, the same request may be redelivered even though the DB change already occurred.

### Behavior when the client does not receive the reply

If the server processed the command successfully but the client timed out due to a delayed reply or network error, the client may resend the same command. For **read-only** operations (`getOrderStatus`), re-execution may be acceptable; for **payment / order creation / placement** commands, you must design a stable idempotency key, such as a unique `requestId` and a table storing processed results.

~~~mermaid
flowchart TD
    A["Receive JMS request"] --> B["Parse + validate"]
    B --> C{"requestId already processed?"}
    C -->|"Yes"| D["Fetch stored result for reply"]
    C -->|"No"| E["Execute business logic in DB transaction"]
    E --> F["Save requestId + result in same DB transaction"]
    F --> G["Build JMS reply"]
    D --> G
    G --> H{"Gateway sends reply successfully?"}
    H -->|"Yes"| I["JMS commit per config"]
    H -->|"Unhandled error"| J["JMS rollback / broker redelivery"]
~~~

For state-mutating commands, idempotency should use a unique constraint and persist a **stable business result** keyed by request ID so retried requests do not cause double effects. The unique constraint and data update must live in the same DB transaction. Decide on a result-retention policy and handle races across multiple consumers.

## 8. Error channel: return a business error or roll back?

If the handler throws an exception, the JMS inbound gateway can send the error to an **`errorChannel`** to turn it into a **valid reply** per contract. For example, when a client queries a non-existent order: returning JSON `NOT_FOUND` may be better than letting the client wait for a JMS timeout.

However, errors must be classified:

| Scenario | Usually appropriate handling | Consequence |
|---|---|---|
| Request missing fields, wrong version | Produce reply `INVALID_REQUEST` or `UNSUPPORTED_VERSION` | Client gets a clear error; if the error flow finishes normally, the transaction may commit |
| Order not found | Produce reply `NOT_FOUND` as a business result | Usually does not need broker redelivery |
| Database temporarily disconnected | Rethrow exception or bounded retry mechanism | Transacted listener can roll back, broker redelivers |
| Downstream timeout | Decide whether to return `TEMPORARY_UNAVAILABLE` or roll back | Must avoid client retries causing duplicate side effects |
| JSON converter cannot read input | Error channel may receive `ErrorMessage` from conversion step | Decide whether to return an error or rethrow for rollback |
| Failed to send JMS reply | Error may cause rollback or client timeout | Do not equate "processed" with "client received" |

### 8.1. Converting an exception into a structured response

Example defining a dedicated error flow **when intentionally acknowledging a business-error request and returning an error response**:

~~~java
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.context.annotation.Bean;

@Bean
public IntegrationFlow orderGatewayErrorFlow() {
    return IntegrationFlow.from("orderGatewayErrors")
            .<ErrorMessage, String>transform(error ->
                    "{\"resultCode\":\"INTERNAL_ERROR\","
                    + "\"message\":\"Request could not be processed\"}")
            .get();
}
~~~

To use this flow, additionally configure `.errorChannel("orderGatewayErrors")` on `Jms.inboundGateway(...)` in section 3. The illustrative error response uses a generic message without leaking stack traces or credentials. In a real application, classify exceptions and build JSON from a schema-compliant DTO; you may include `requestId` from the original request once validated, while avoiding echoing untrusted input directly into error messages.

**Critical consequence:** if the error flow **turns an exception into a successful Spring reply**, the listener may commit the JMS transaction because the error was handled. For infrastructure errors requiring rollback/redelivery, the error flow must **rethrow the exception** (or omit error channel handling per strategy). Since Spring Integration 4.2, conversion errors in the JMS inbound gateway can also be routed to the error channel.

### 8.2. An error does not automatically equal a JMS reply

Without appropriate error-channel configuration, an exception from a handler does not automatically become an error-carrying JMS response; the client may simply hit a **timeout**. Patterns such as sending an `ErrorMessage` to `nullChannel` or catching errors and returning `null` can hide failures and interfere with rollback. Never swallow exceptions blindly.

If gateway-level retries are needed, Spring Integration 6.3+ supports `retryTemplate` and `recoveryCallback` for internal gateway operations. This feature is version-dependent; configure bounded attempts and backoff to avoid holding consumers too long, and verify which steps already had side effects before retrying.

## 9. Tuning the listener container and operations

The inbound gateway uses a JMS `MessageListenerContainer` to manage request-receiving consumers. Common tuning parameters:

| Setting | Role | Considerations |
|---|---|---|
| `concurrentConsumers` | Minimum consumers receiving requests in parallel | Increase when handlers are fast, independent, and resources suffice |
| `maxConcurrentConsumers` | Maximum consumers when the container supports dynamic scaling | Load-test to avoid saturating downstream DB/HTTP |
| `sessionTransacted` | JMS receive/reply send within listener transaction | Verify provider behavior and exception propagation |
| `receiveTimeout` of listener container | Wait interval when internally polling for JMS messages | Distinct from client `JmsTemplate.receiveTimeout` |
| `recoveryInterval` / `BackOff` | JMS connection recovery strategy | Emit metrics and alerts when the listener stops receiving requests |
| `destinationName` / `requestDestination` | Request-receiving queue/topic | Wrong destination causes client timeouts even while the broker is healthy |

With request-reply, **concurrency determines not only throughput but also how many requests can concurrently wait on handlers/replies**. If each request takes 2 seconds and there is only one consumer, the backlog grows quickly under concurrent client traffic. Raising consumer count must be paired with DB pool, memory, broker connections, and timeout budgets. Requests may complete **out of send order** when executed in parallel; clients must rely on correlation.

When using a **queue**, multiple listener containers/instances can compete to receive requests. With a **topic**, every subscription can receive a copy of the request and generate multiple replies unless the contract is carefully designed; request-reply over a queue is usually easier to control. If a topic is mandatory, decide `pubSubDomain` and durable/shared subscriptions according to the JMS provider.

### Connection lifecycle

- When the application starts, the listener container opens connections/sessions/consumers and registers callbacks; when the endpoint stops, by default the container stops and releases connections/consumers depending on version/config.
- If the broker disconnects temporarily, the listener container can recover; monitor **active consumer count** and **oldest waiting request age**, not merely whether the Java process is alive.
- When redeploying while requests are in flight, clients may time out and retry; JMS session rollback/redelivery depends on transactions and broker policy.
- Do not store pending-request state solely in RAM if business rules require continuity across restarts; for write commands, use idempotency and a suitably durable result store.

**Essential metrics:** requests received/sec, replies sent successfully/sec, business error rate, p50/p95/p99 processing latency, client timeout rate, redeliveries, queue depth, age of oldest request, active consumers, and broker reconnect status. Logs should include `requestId`, JMS message ID, and correlation ID when available; do not log full payloads containing personal data.

## 10. Hands-on exercise: querying order status from ERP

Use a test broker with the `orders.status.request` queue and a Spring Integration application providing `OrderStatusService`.

1. **Happy path:** start the gateway as in section 3, send request `ORD-700` via `JmsTemplate.sendAndReceive`; verify the reply has the matching `requestId`, `resultCode`, and `status`.
2. **Missing JMSReplyTo:** send a request from a producer without setting reply-to; observe behavior before configuring a default reply queue, then add `defaultReplyQueueName` and a consumer on that queue.
3. **Concurrent requests:** run multiple clients with different requests; inspect `JMSCorrelationID` and avoid matching responses by arrival order.
4. **Business error:** send a request missing `orderId`; configure an error flow returning `INVALID_REQUEST` and verify the client receives an error reply with a clear schema.
5. **Infrastructure error:** make the service throw an exception when the DB is unavailable; with a transacted listener, observe rollback/redelivery and broker retry/DLQ counts.
6. **Timeout:** add server delay longer than the client's `JmsTemplate.receiveTimeout`; observe the client receiving `null`/timeout and analyze the late reply.
7. **Async path:** route requests into an `ExecutorChannel`, observe transaction boundaries and reply timeouts; explain why downstream errors do not necessarily roll back the JMS request.
8. **Idempotency:** change the service into an order-creation command with a stable `requestId`; send twice and verify the database creates only one order.
9. **Recovery:** stop the broker or gateway and restart it; observe listener status, queue backlog, client retries, and correlation.

### Key checks

| What to verify | How to observe |
|---|---|
| Request decoded properly by converter | Handler receives `String` instead of raw JMS object when using `TextMessage` |
| Reply uses correct JMS destination | Inspect `JMSReplyTo` or default reply queue |
| Reply matches request | Inspect `JMSCorrelationID`/JMS message ID per contract |
| Error rolls back or commits | Observe redelivery and message count in the queue |
| Timeout does not cause duplicate processing | Resend the same `requestId` and check the unique constraint |
| Broker disconnection recovers | Listener resumes receiving new requests after recovery |

Integration tests should use a **real JMS broker or provider-matching test container**. Mocking `MessageChannel` or the handler only verifies local logic; it cannot prove reply destination, correlation, transactions, redelivery, or recovery.

### Self-check questions

1. Why does a JMS inbound gateway require a reply while a JMS message-driven channel adapter does not?
2. How do `JMSReplyTo` and `JMSCorrelationID` solve two different problems?
3. If a client uses a temporary queue and times out before the server sends the reply, what can happen?
4. When should `defaultReplyQueueName` be configured? Why does a shared reply queue require correlation?
5. What is the difference between timeout on the client `JmsTemplate`, gateway `replyTimeout`, and DB timeout?
6. Why can turning an error into an error reply cause the JMS transaction to commit?
7. Why does a transacted listener still need idempotency when the handler writes to a database?
8. If a client wants to emit an event without expecting a response, which JMS endpoint should be chosen?

## 11. References

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): inbound/outbound gateways, `JMSReplyTo`, message conversion, error channels, transactions, and correlation.
- [Spring Integration API — JmsInboundGatewaySpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsInboundGatewaySpec.html): `requestDestination`, `defaultReplyQueueName`, `extractRequestPayload`, `extractReplyPayload`, and `replyToExpression`.
- [Spring Framework API — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `sendAndReceive` and temporary reply destination mechanics.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): reply channels, request/reply timeouts, and interaction between gateways and Spring Message channels.

**Remember:** a JMS inbound gateway turns a JMS request into a Spring Message, waits for downstream to produce a Spring reply, and sends a JMS reply back to the client's destination. Correct behavior depends simultaneously on the payload contract, `JMSReplyTo`, correlation, timeouts, transactions, error handling, and idempotency; sending a reply does not automatically guarantee that database side effects were committed atomically with JMS.

# JMS inbound channel adapter polling

## 1. Problem: polling messages from JMS on a schedule

In Spring Integration, a **polling JMS inbound channel adapter** is a one-way entry point that brings messages from a JMS destination (typically a queue) into a processing flow through a `MessageChannel`. This component proactively invokes `JmsTemplate.receive()` on a **poller** schedule. It is suitable when the application needs to control the timing or cadence of data ingestion, such as scanning a queue containing synchronization requests from a legacy ERP system every few seconds.

This is one of the external-system connection mechanisms in the **SPRING_INTEGRATION_ADAPTERS** module: an inbound adapter receives data, an outbound adapter sends data, a gateway handles request–reply exchanges, and a `MessageChannel` decouples the JMS source from business processing steps. This topic focuses in depth on the **polling JMS inbound channel adapter** and does not replace the full knowledge of file, SFTP, HTTP, AMQP, Kafka, or database adapters.

Running example: an ERP system sends order JSON into the `orders.in` queue. The Spring Integration application scans the queue every 5 seconds, fetches up to 10 messages per poll, converts them into Spring Messages, and hands them over to an order-import handler. The business domain tolerates a delay of a few seconds; if immediate reaction upon message arrival at the broker is required, a message-driven solution is usually more appropriate.

### Data model and path

~~~mermaid
flowchart LR
    A["ERP / external system"] -->|"JMS TextMessage"| B[("Broker: orders.in")]
    P["Poller: fixedDelay 5 seconds"] -->|"Triggers receive()"| C["JMS inbound adapter"]
    B -->|"JmsTemplate.receive()"| C
    C -->|"Spring Message"| D["MessageChannel"]
    D --> E["Validate / process order"]
    E --> F[("Database")]
~~~

Execution flow of a single poll:

1. `TaskScheduler` triggers the poller according to `fixedDelay`, `fixedRate`, or cron.
2. The inbound adapter calls `receive()` on the JMS destination. If there is no message and non-blocking receive mode is used, the poll attempt ends immediately.
3. `MessageConverter` converts the JMS message into the Spring Message payload; `JmsHeaderMapper` maps the appropriate headers.
4. The adapter sends the Spring Message to the `MessageChannel`; the downstream consumer receives and processes it.
5. If `maxMessagesPerPoll` is greater than 1, the poller can repeat the receive operation within the same poll, stopping when the limit is reached or the source has no more messages.

**Distinguishing two polling cadences:** the poller at the **JMS input** decides when to call `receive()`; if you later place the message onto a `QueueChannel` and have another polling consumer, that consumer has its **own schedule for pulling from `QueueChannel`**. Do not confuse these two layers.

## 2. Components to understand

| Component | Role | Key considerations |
|---|---|---|
| JMS broker and `Destination` | Stores/distributes messages, e.g., the `orders.in` queue | Queues suit the model where one message is processed by one consumer; topics have different subscription semantics |
| `ConnectionFactory` | Creates JMS connections to the broker | Use a compatible provider and configure connection, authentication, and connection recovery |
| `JmsTemplate` | Provides synchronous JMS receive calls | `receiveTimeout` determines whether a single receive waits for a message |
| `JmsDestinationPollingSource` | `MessageSource` used in the JMS inbound adapter | Retrieves JMS messages and converts them into Spring Messages |
| `SourcePollingChannelAdapter` and poller | Triggers `MessageSource.receive()` on a schedule | Determines intervals between polls, maximum messages per poll, and transaction advice |
| `MessageChannel` | Delivers messages to the next step | `DirectChannel` keeps handler invocation synchronous on the same thread; asynchronous channels change processing boundaries |
| Message handler | Validates, transforms, persists data, or calls services | Must be designed to be idempotent with consistent error handling |

This adapter **does not send responses back to the JMS producer**. When a request/reply model is needed, see the JMS inbound/outbound gateway; when sending messages to the broker is needed, use the JMS outbound channel adapter.

## 3. Configuration with Spring Integration Java DSL

The following example uses the familiar API of Spring Integration 6+ and Jakarta JMS (older Spring versions may use the `javax.jms` package). The project needs `spring-integration-jms` and a JMS client/starter library matching the broker; Maven example when versions are managed by the Spring Boot BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Add the JMS provider / Spring Boot JMS starter appropriate for the broker. -->
~~~

`ConnectionFactory` must be a bean already configured to connect to the broker. The section below illustrates the integration point; broker address, credentials, and queue creation depend on the provider and are not assumed.

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class OrderJmsPollingConfig {

    @Bean
    public IntegrationFlow importOrdersFromJms(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(
                Jms.inboundAdapter(connectionFactory)
                        .destination("orders.in")
                        // Do not hold the poller thread waiting when the queue is empty.
                        .configureJmsTemplate(template ->
                                template.receiveTimeout(-1)),
                endpoint -> endpoint.poller(poller ->
                        poller.fixedDelay(5000)
                                .maxMessagesPerPoll(10)))
                .channel("ordersInput")
                .handle(String.class, (jsonBody, headers) -> {
                    // Demo: replace with validation service, DB persistence, and idempotency handling.
                    System.out.println("Received order: " + jsonBody);
                    return null; // One-way handler, produces no reply.
                })
                .get();
    }
}
~~~

`.destination("orders.in")` selects the queue to read from; the queue name must match the broker configuration. `.channel("ordersInput")` specifies the Spring Message delivery point (the DSL can create a `DirectChannel` if this channel has not been declared). The handler uses `String.class` because the example assumes the producer sends `TextMessage`; if the producer sends `BytesMessage` or another format, adjust the converter and handler accordingly.

To push a test message into the queue using Spring JMS components in the same connection environment:

~~~java
// jmsTemplate is a bean configured with the same JMS provider.
jmsTemplate.convertAndSend(
        "orders.in",
        "{\"eventId\":\"evt-1001\",\"orderId\":\"ORD-42\",\"total\":125000}");
~~~

When the broker is running, the message is valid, and the flow is started, after the corresponding poll you will see the payload in the log. The `System.out.println` statement is for illustration only; production implementations must replace it with business processing and structured error tracking.

### Equivalent XML configuration for the polling schedule

In an application using Spring Integration's XML namespace, the corresponding key part is:

~~~xml
<int:channel id="ordersInput"/>

<int-jms:inbound-channel-adapter
        id="orderJmsInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.in"
        channel="ordersInput">
    <int:poller fixed-delay="5000" max-messages-per-poll="10"/>
</int-jms:inbound-channel-adapter>
~~~

The XML example is a component configuration snippet; the application also needs namespace declarations, the `jmsConnectionFactory` bean, and a consumer for `ordersInput`. It shows that `<int:poller>` is an essential element for the inbound adapter to actively pull messages on a schedule.

## 4. Choosing the polling schedule and receive limits

| Parameter | Meaning | Considerations |
|---|---|---|
| `fixedDelay(5000)` | Waits 5 seconds **after the previous poll completes** before starting the next one | Easy to control rest intervals, suitable for small-batch processing |
| `fixedRate(5000)` | Schedules on uniform 5-second marks; processing duration can affect actual execution | Use when trigger cadence matters; do not assume polls run in parallel |
| `cron(...)` | Polls only during specific time windows | Use for sync windows or off-peak hours |
| `maxMessagesPerPoll(10)` | At most 10 message receives per poll, or stops early when the source has no messages | Tune according to backlog, handler speed, and resource-yielding needs |
| `receiveTimeout(-1)` | With `JmsTemplate`, performs a **non-waiting** receive (`receiveNoWait`) | Avoids letting each empty-queue scan occupy a scheduler thread for long |
| Positive `receiveTimeout` | Can wait up to the configured duration in a single receive | Consider total wait time across multiple receives and the number of scheduler threads |

For `SourcePollingChannelAdapter`, the default value of `maxMessagesPerPoll` is **1** if not configured. For example, with `fixedDelay = 5 s` and `maxMessagesPerPoll = 10`, if processing is very fast, a single instance has the capacity to fetch roughly up to 10 messages per cycle of just over 5 seconds; this is **not a throughput guarantee** because handler, broker, network, and transaction times can lengthen each cycle. When the queue continuously has data, increasing the limit can reduce backlog but also causes a single poll to hold the thread longer.

A few notes:

- When the queue is empty, `receive()` returns `null` if no message arrives within the wait time; the poller ends the current poll rather than sending a Spring Message with a `null` payload.
- If `maxMessagesPerPoll` is set negative, the poller may keep receiving until the source returns `null`. With a source that always has messages, a poll can drag on excessively and slow down shutdown responsiveness; a concrete limit is usually preferable.
- `receiveTimeout(-1)` is an intentional choice in the example. The default depends on how the adapter creates `JmsTemplate`, consumer caching settings, and version; do not assume every configuration behaves in non-waiting mode.
- Increasing receive threads or using multiple consumers must account for queue ordering, independence between messages, and downstream load capacity.

## 5. Message contract: from JMS to Spring Integration

When `extractPayload` is enabled (the default), the converter creates the payload from the body of the JMS message. With the common `SimpleMessageConverter`:

| Input JMS type | Typical Spring Message payload | How to handle |
|---|---|---|
| `TextMessage` | `String` | Parse JSON/XML, validate schema and version |
| `BytesMessage` | `byte[]` | Decode according to the agreed charset/format |
| `ObjectMessage` | `Serializable` object | Be cautious of class compatibility and deserialization risks; prefer neutral formats like JSON |

JMS metadata such as message ID, correlation ID, type, and certain properties are mapped into Spring Message headers depending on `JmsHeaderMapper`. Do not assume every property or header is preserved across all adapters and converters; verify the actual producer/consumer contract.

A useful order contract might look like:

~~~json
{
  "eventId": "evt-1001",
  "schemaVersion": 1,
  "orderId": "ORD-42",
  "total": 125000
}
~~~

The handler should check `schemaVersion`, required fields, and data types before writing to the DB. Use `eventId` as the idempotency key on the receiving side to guard against duplicate processing when the broker redelivers or the producer resends. `JMSMessageID` is useful for tracing a single delivery; it does not always replace a stable business ID across multiple logical replays.

If you need to receive the raw `jakarta.jms.Message` object, you can configure `extractPayload(false)` on the adapter, but doing so couples downstream components to the JMS API and provider session/lifecycle. For standard business flows, converting early to a domain payload and selected headers reduces coupling.

## 6. Transactions, acknowledgement, and redelivery

This is the most error-prone boundary in JMS polling: **pulling a message from the broker does not mean downstream business processing has completed**.

### Without an enclosing transaction

1. The poller calls `JmsTemplate.receive()`.
2. The JMS session acknowledges/commits the receive according to the template's mode and configuration.
3. The adapter sends the Spring Message to the `MessageChannel`.
4. The handler encounters a processing error or fails to write to the DB.

If the receive step was already acknowledged before step 4, the broker might not redeliver the message even though business processing failed. Simply enabling `sessionTransacted = true` on the JMS inbound adapter alone also **does not guarantee** rollback on downstream errors: according to the Spring Integration documentation, the receive call's own transaction may commit before the message is sent to the channel.

### When rollback based on handler outcome is needed

Place transaction advice on the **poller** using `JmsTransactionManager`, so that receiving and passing through the **synchronous** processing chain share the same JMS transaction boundary. Example of adding the bean:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.connection.JmsTransactionManager;

@Bean
public JmsTransactionManager jmsTransactionManager(ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

Then, in the endpoint configuration of the flow in section 3, replace the poller with:

~~~java
endpoint -> endpoint.poller(poller ->
        poller.fixedDelay(5000)
              .maxMessagesPerPoll(10)
              .transactional(jmsTransactionManager))
~~~

Here `jmsTransactionManager` is the bean additionally injected into the flow configuration method. This snippet **replaces** the previous poller configuration rather than creating a second flow reading from `orders.in`.

Conditions for rollback on business errors to work as expected:

- The processing path must remain **synchronous within the transaction scope** (for example, a `DirectChannel` and a handler running on the same thread). If you route the message into an `ExecutorChannel` or `QueueChannel`, downstream work may run after the poller transaction has already ended.
- Errors must propagate out of the handler so the transaction marks rollback. If you catch the exception, only log it, and return normally, the poller may commit.
- The broker/provider must support session transactions, redelivery policies, and an appropriate dead-letter queue. Do not assume an error will be retried indefinitely or moved to a DLQ automatically.
- `JmsTransactionManager` coordinates the local JMS transaction; it **does not** automatically turn a DB update and a JMS acknowledgement into an atomic transaction. When coordinating DB and broker, use idempotency, retryable processing patterns, or distributed transaction mechanisms when genuinely needed and supported.

**Delivery expectation:** with proper transaction configuration and synchronous error propagation, messages may be redelivered after a rollback. Therefore, the business logic must tolerate **at-least-once** delivery and handle duplicates. Do not claim `exactly-once` based solely on a single configuration option.

## 7. Error handling and operations

| Scenario | Symptom | Resolution |
|---|---|---|
| Broker disconnected | JMS errors or poller unable to read queue | Monitor connection/consumer; configure provider recovery; alert when backlog grows |
| Empty queue | `receive()` finds no message | Normal state; use non-waiting timeout for lightweight scans |
| Malformed JSON schema | Converter/handler throws error | Classify data errors, log safe tracing details, route to DLQ/quarantine per policy |
| DB temporarily unavailable | Handler throws exception | Roll back if enclosed in a transaction, retry with bounded attempts and sensible backoff |
| Duplicate message | Same `eventId` processed multiple times | Unique constraint or inbox/idempotency store keyed by `eventId` |
| Growing backlog | High queue latency, prolonged import time | Measure ingress/egress rates, optimize handler, consider switching from polling to message-driven |

Spring Integration provides `errorChannel` and a mechanism to send `ErrorMessage` when an endpoint raises an error in applicable situations. However, **sending an error to a channel does not by itself guarantee rollback, retry, or DLQ routing**. You must verify whether the exception is rethrown across the transaction advice or swallowed by an error handler, and configure broker redelivery/DLQ explicitly.

In production, monitor at minimum: queue depth, oldest message age, count of messages received/processed successfully, count of processing failures, redelivery count, handler duration, latency between emission and processing, JMS connection status, and poller status. Logs should include `eventId`, JMS message ID/correlation ID if available, and destination name; avoid logging entire payloads containing sensitive data.

### Idempotency design example

For a message with `eventId = evt-1001`, the handler can:

1. Open a DB transaction and insert `evt-1001` into a `processed_event` table with a unique constraint.
2. If the key already exists, treat the message as already processed and exit safely.
3. If the key does not exist, validate and update the order within the same DB transaction, then commit.
4. Report success to the poller only after synchronous work completes; on error, let the exception be handled according to the transaction/retry strategy.

This approach reduces the risk of duplicate writes when a message is replayed. Design order-import states, unique keys, and commit ordering properly for the domain; do not infer that JDBC and JMS will commit atomically together.

## 8. When to use polling vs. switching to message-driven?

| Criterion | JMS inbound **polling** | JMS **message-driven** inbound adapter |
|---|---|---|
| Receive trigger | Scheduler calls `receive()` on a schedule | JMS listener container receives and pushes messages when available |
| Latency when queue has few messages | Can equal the wait until the next poll | Typically lower, close to message arrival time |
| Rate throttling | Explicit via fixed delay/rate, cron, messages per poll | Tuned via listener container, concurrency, and downstream load |
| Typical purpose | Batch, periodic sync, delay-tolerant systems | Continuous event processing, medium/high load, fast-response requirements |
| Transactions | Must consider transaction on poller and synchronous downstream | Listener container typically has direct transaction/acknowledgement support |

The Spring Integration documentation recommends message-driven for **most JMS receive scenarios** since there is no need to wait for a polling cycle. Use polling when operational requirements specifically demand a scan schedule, controlled cadence, or periodic load. Do not choose polling simply out of familiarity with `@Scheduled` if the SLA requires near-instant reception.

## 9. Hands-on verification

In a test environment with a broker and the `orders.in` queue:

1. **Happy path:** send a valid `TextMessage`; verify the handler runs after the poll and receives the expected payload.
2. **Empty queue:** leave the queue empty; verify the flow does not emit dummy messages and the scheduler remains active.
3. **Batch limit:** send more than 10 messages before a poll; verify `maxMessagesPerPoll(10)` caps the number of receives in that poll and the remaining backlog is processed in subsequent polls.
4. **Data error:** send malformed JSON against the schema; verify error handling, DLQ policy, and whether the message is redelivered.
5. **Transient error:** simulate the handler throwing an exception in a flow with a transactional poller; observe rollback/redelivery, then verify `eventId` does not produce duplicate records.
6. **Stop/restart:** stop the endpoint or application, put new messages into the queue, restart, and verify pending messages are processed.

When testing transactions and redelivery, use a real broker/provider or a container environment with matching behavior; mocking `JmsTemplate` only verifies part of the method-invocation logic.

### Self-check questions

1. Why does `maxMessagesPerPoll = 10` not mean the system is guaranteed to process 10 messages every 5 seconds?
2. When is `receiveTimeout(-1)` beneficial and why can receive timeout affect scheduler threads?
3. Why is simply enabling `sessionTransacted` on the adapter insufficient to roll back handler errors?
4. What changes if `DirectChannel` is replaced by `ExecutorChannel` in a flow with a transactional poller?
5. For a business flow requiring message reception within tens of milliseconds, should you choose polling or message-driven? Why?

## References

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): inbound channel adapter configuration, message conversion, transactions, and message-driven comparison.
- [Spring Integration Reference — Channel Adapter](https://docs.spring.io/spring-integration/reference/channel-adapter.html): `SourcePollingChannelAdapter`, `maxMessagesPerPoll`, and poller mechanics.

**Remember:** A JMS polling inbound adapter is the boundary transferring messages from a broker into Spring Integration on a schedule. Flow correctness depends simultaneously on receive frequency, channel type, payload/header contracts, transactions around synchronous processing, redelivery strategy, and idempotency.

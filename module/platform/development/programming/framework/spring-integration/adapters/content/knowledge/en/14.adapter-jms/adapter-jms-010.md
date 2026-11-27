# Session acknowledgment and transactions in JMS

## 1. Why does message acknowledgment matter?

An ERP system sends orders into the JMS queue `orders.in`. The Spring Integration application receives the message, validates JSON, and saves the order into PostgreSQL. If the database is failing, what happens to the message just received?

- If the **broker already considers the message acknowledged**, the message may be removed from the queue even though the order was not saved.
- If the **JMS session rolls back**, the broker can redeliver the message when a consumer receives next.
- If the database committed while the JMS session did not yet commit and the app crashed, the same message may arrive again, creating a risk of **duplicate writes**.

Therefore, we must distinguish three milestones: **receiving the JMS message**, **completing business logic**, and **acknowledging/committing at the broker**. Only by understanding their ordering and boundaries can we configure a reliable flow.

In the **SPRING_INTEGRATION_ADAPTERS** module, inbound/outbound adapters, gateways, pollers, and `MessageChannel`s connect external systems across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. For JMS, **session acknowledgment and transactions** determine when a receive/send is considered complete, when rollback happens, and whether integration flow errors propagate back to the broker.

After this lesson, you should be able to:

1. Distinguish JMS acknowledgment from the commit/rollback of a JMS transaction.
2. Choose among `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, `DUPS_OK_ACKNOWLEDGE`, or transacted sessions as required.
3. Configure message-driven listeners and transactional pollers in Spring Integration.
4. Understand `JmsTransactionManager`, exception propagation across `DirectChannel`, and the boundary of `ExecutorChannel`.
5. Design idempotency, retries, DLQs, and outboxes when JMS coordinates with a database.

## 2. Path of a JMS message and three levels of success

~~~mermaid
sequenceDiagram
    participant Broker as JMS broker
    participant Container as Listener container
    participant Adapter as JMS inbound adapter
    participant Handler as Spring Integration handler
    participant DB as PostgreSQL

    Broker->>Container: JMS message
    Container->>Adapter: Message-receive callback
    Adapter->>Handler: Spring Message via DirectChannel
    Handler->>DB: Write data in DB transaction
    DB-->>Handler: DB commit or exception
    Handler-->>Adapter: Success or exception
    Adapter-->>Container: Callback ends / throws error
    Container->>Broker: JMS acknowledge, commit, or rollback
~~~

The diagram illustrates the **synchronous processing path**. With some acknowledgment modes, the broker may receive acknowledgment **before** the handler executes; exact details depend on the listener container and configuration.

| Milestone | What has happened | What is not yet guaranteed |
|---|---|---|
| **Delivered/received** | Broker delivered the message to the consumer | Handler has not necessarily succeeded |
| **Business completed** | Handler may have finished and DB committed | Broker has not necessarily committed the JMS operation |
| **Acknowledged/committed** | Provider marked receipt successful on the session | Does not prove another downstream DB/HTTP/Kafka step completed |

**Ack and commit are not synonymous.** In a **non-transacted** session, the acknowledgment mode dictates how receipt is confirmed. In a **transacted** session, `Session.commit()` or `Session.rollback()` controls JMS operations in the transaction; do not call `Message.acknowledge()` as a substitute for commit.

### JMS Session and resource management responsibility

`jakarta.jms.Session` is the working context for JMS messages, producers, and consumers. Sessions are normally **not safe for concurrent multi-threaded use**. Spring manages resources on the application's behalf:

- `JmsTemplate` acquires/creates a session for `send()`, `receive()`, or to participate in an active JMS transaction.
- `DefaultMessageListenerContainer` creates listener tasks and JMS consumers/sessions to receive continuously from the broker.
- `ConnectionFactory` provides provider connections; it can be wrapped for caching/pooling, but does not itself govern business commits.
- `MessageChannel` transports Spring Messages inside the app; it is **not** a JMS session or transaction manager.

When a listener container runs four consumers, each listener task operates with its own appropriate JMS resources; **there is no single session/transaction spanning all messages simultaneously processed across all four consumers**.

## 3. JMS acknowledgment modes

JMS defines modes for **non-transacted sessions**. Distinguish JMS API semantics from how a Spring listener container executes callbacks.

| Mode | Goal | Reliability notes |
|---|---|---|
| `Session.AUTO_ACKNOWLEDGE` | Provider/container acknowledges automatically | With `DefaultMessageListenerContainer`, acknowledgment may happen before the listener runs; handler exceptions do not guarantee redelivery |
| `Session.CLIENT_ACKNOWLEDGE` | Acknowledges via `Message.acknowledge()` or container management | With Spring listeners, may provide **best-effort redelivery** on errors; not equivalent to a JMS transaction |
| `Session.DUPS_OK_ACKNOWLEDGE` | Allows the provider to delay/batch acknowledgments | Can redeliver messages; must tolerate duplicates |
| **Transacted session** | JMS `commit()` / `rollback()` determines outcome | Rollback can trigger redelivery; covers only operations in that JMS transaction |

Some JMS providers offer extended modes such as **INDIVIDUAL_ACKNOWLEDGE**; this is not a portable Jakarta JMS standard feature. Do not design solutions relying on it without verifying provider and version support.

### 3.1. `AUTO_ACKNOWLEDGE`: why can messages be lost when a handler fails?

For `DefaultMessageListenerContainer` (DMLC), Spring Framework notes that acknowledgment can occur **before the listener executes**. Thus:

~~~text
Broker delivers message
    -> DMLC acknowledges under AUTO_ACKNOWLEDGE
    -> Handler calls database
    -> Database times out, handler throws exception
    -> JMS message may NOT be redelivered
~~~

`SimpleMessageListenerContainer` uses provider-driven callbacks and differs in details from DMLC, yet AUTO_ACK is still not a reliable choice for critical business queues. Do not assume the JMS provider automatically knows a downstream handler failed if the container does not propagate the error to the acknowledgment boundary.

### 3.2. `CLIENT_ACKNOWLEDGE` and the scope of `acknowledge()`

In plain JMS, a callback can explicitly call:

~~~java
// Illustration in a JMS listener managing its own session.
void onMessage(jakarta.jms.Message message) throws jakarta.jms.JMSException {
    processBusiness(message);
    message.acknowledge();
}
~~~

Under standard `CLIENT_ACKNOWLEDGE`, `Message.acknowledge()` acknowledges **all messages consumed by the session**, not necessarily just the current message. Therefore, never stash a JMS Message and call `acknowledge()` from another thread when a session/container manages the processing lifecycle.

A Spring listener container can automatically acknowledge after a successful callback instead of requiring a Spring Integration handler to call `acknowledge()`. With DMLC, this mode can provide **best-effort** redelivery when the callback throws an exception; however, exact reliability still depends on the provider and failure timing.

### 3.3. `DUPS_OK_ACKNOWLEDGE`

The provider may defer acknowledgments to optimize throughput. In return, duplicate deliveries must be accepted as normal. This is not a solution for processing orders, payments, or external side effects once.

### 3.4. `sessionTransacted=true`: do not use acknowledgment modes in place of commit

When a session is transacted, JMS sends/receives are governed by **commit** or **rollback**. The `sessionTransacted` flag and transaction manager are the primary settings to configure—not pairing `CLIENT_ACKNOWLEDGE` and assuming the callback commits at the right time.

Note: **redelivery alone does not guarantee an exactly-once business effect**. A JMS transaction manages only the JMS resource; it does not atomically commit with PostgreSQL.

## 4. Defaults of the message-driven adapter and listener container

A major source of confusion: **standalone DMLC** and a **message-driven channel adapter whose container is created by Spring Integration** can have **different transaction defaults**.

Since **Spring Integration 4.2**, the message-driven channel adapter defaults to `acknowledge="transacted"` **when the adapter creates the container itself**. If you supply an **external container**, the application author must configure transactions/acknowledgment on that container explicitly. With DMLC, Spring Integration recommends transacted mode to reduce message loss.

| Endpoint style | Where to configure | Key point to remember |
|---|---|---|
| `Jms.messageDrivenChannelAdapter(connectionFactory)` | DSL `configureListenerContainer(...)` or XML adapter | Adapter creates the listener container and defaults to transacted |
| `Jms.messageDrivenChannelAdapter(externalContainer)` | `DefaultMessageListenerContainer` bean | Do not assume transacted default from the adapter |
| Standalone `DefaultMessageListenerContainer` | `setSessionTransacted(true)` / transaction manager directly | Must check Spring JMS defaults |
| `SimpleMessageListenerContainer` | Container's own session mode/transaction | Does not support external transactions the way DMLC does |

### 4.1. Java DSL using a transacted listener container

Example with Spring Integration 6+, Java 17+, and Jakarta JMS; assumes the broker has queue `orders.in` and the app has a working `ConnectionFactory` bean:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Configuration
@EnableIntegration
public class OrderInboundJmsConfiguration {

    @Bean
    public DefaultMessageListenerContainer orderListenerContainer(
            ConnectionFactory connectionFactory) {
        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.in");
        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(4);
        container.setSessionTransacted(true);
        return container;
    }

    @Bean
    public IntegrationFlow orderInboundFlow(
            DefaultMessageListenerContainer orderListenerContainer,
            OrderImportService orderImportService) {
        return IntegrationFlow
                .from(Jms.messageDrivenChannelAdapter(orderListenerContainer))
                .handle(String.class, (json, headers) -> {
                    orderImportService.importOrder(json);
                    return null;
                })
                .get();
    }
}
~~~

`OrderImportService` is a business service implemented by the app. The handler stays on a **synchronous path**, returning `null` because the inbound channel adapter is one-way. For a `TextMessage`, the standard `SimpleMessageConverter` produces a `String` payload; if the producer sends another format, use a compatible converter/handler.

When the handler throws an exception and no error flow absorbs it, the listener container can roll back the JMS session. When the callback finishes normally, the container can commit. **If multiple listener container beans of the same type exist**, use `@Qualifier` to avoid ambiguous injection.

An independently declared container has its own Spring lifecycle; test listener attachment and start/stop coordination, and do not share the same container unintentionally across two distinct endpoints.

### 4.2. Java DSL letting the adapter create its own container

~~~java
IntegrationFlow.from(
        Jms.messageDrivenChannelAdapter(connectionFactory)
                .destination("orders.in")
                .configureListenerContainer(container ->
                        container.sessionTransacted(true)
                                .concurrentConsumers(2)
                                .maxConcurrentConsumers(4)))
        .handle(String.class, (json, headers) -> {
            orderImportService.importOrder(json);
            return null;
        })
        .get();
~~~

This is a fragment inside a `@Bean` method with `connectionFactory` and `orderImportService` available. It is an **alternative** to section 4.1; do not register both reading `orders.in` simultaneously if only one logical workload is intended.

### 4.3. XML namespace

~~~xml
<int:channel id="ordersInput"/>

<int-jms:message-driven-channel-adapter
        id="ordersInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.in"
        channel="ordersInput"
        acknowledge="transacted"
        concurrent-consumers="2"
        max-concurrent-consumers="4"/>

<int:service-activator
        input-channel="ordersInput"
        ref="orderImportService"
        method="importOrder"/>
~~~

The XML fragment needs `int`/`int-jms` namespaces and the corresponding beans and handlers. If supplying `container="..."`, configure transactions on the referenced container; do not rely on adapter attributes that only apply when the adapter creates the container itself.

## 5. Why does polling inbound need a **transactional poller**?

A polling inbound adapter differs from message-driven in how it is triggered:

~~~text
Poller triggers
    -> JmsTemplate.receive("orders.in")
    -> receive call completes
    -> Adapter publishes Spring Message to channel
    -> Downstream handler processes
~~~

If you only set `sessionTransacted=true` on `JmsTemplate` when **there is no transaction wrapping the poll**, the template may commit JMS right after `receive()`, **before** the Spring Message is dispatched. A handler exception then **cannot roll back** the already-committed JMS receive.

To span both message retrieval and synchronous dispatch/handling, use a **transactional poller** with `JmsTransactionManager`.

### 5.1. Declaring a manager for the JMS resource

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.connection.JmsTransactionManager;

@Bean("orderJmsTxManager")
public JmsTransactionManager orderJmsTxManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

`JmsTransactionManager` manages **local JMS transactions** for a `ConnectionFactory`, binding the resource session to the transactional thread; it does not open a PostgreSQL transaction on its own.

### 5.2. Java DSL transactional polling flow

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.jms.connection.JmsTransactionManager;

@Bean
public IntegrationFlow orderPollingFlow(
        ConnectionFactory connectionFactory,
        JmsTransactionManager orderJmsTxManager,
        OrderImportService orderImportService) {

    return IntegrationFlow.from(
            Jms.inboundAdapter(connectionFactory)
                    .destination("orders.in")
                    .configureJmsTemplate(template ->
                            template.receiveTimeout(-1)),
            endpoint -> endpoint.poller(poller ->
                    poller.fixedDelay(5000)
                            .maxMessagesPerPoll(5)
                            .transactional(orderJmsTxManager)))
            .handle(String.class, (json, headers) -> {
                orderImportService.importOrder(json);
                return null;
            })
            .get();
}
~~~

- `fixedDelay(5000)` sets the poll interval, **not** receive timeout.
- `receiveTimeout(-1)` makes JMS receive non-blocking when the queue is empty.
- `maxMessagesPerPoll(5)` caps messages fetched in a single poll, **not** consumer count.
- `transactional(orderJmsTxManager)` wraps polling in transaction advice so **synchronous** receive and dispatch share the same JMS transaction.

If the flow passes the message into an `ExecutorChannel` or `QueueChannel` before the handler, failures on the subsequent thread/consumer typically occur **outside the poller's transaction boundary** and cannot roll back the received JMS message.

For continuous JMS events needing low latency, the message-driven inbound adapter is the usual choice; polling remains useful when business rules dictate scheduled/batched pickup.

## 6. `JmsTemplate` and outbound adapter transactions

Transactions also apply to sending JMS messages. To commit/roll back two sends together in a **local JMS transaction**, use `JmsTransactionManager` with `JmsTemplate`:

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JmsEventPublisher {
    private final JmsTemplate jmsTemplate;

    public JmsEventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "orderJmsTxManager")
    public void publishPair(String firstEvent, String secondEvent) {
        jmsTemplate.convertAndSend("orders.events", firstEvent);
        jmsTemplate.convertAndSend("audit.events", secondEvent);
    }
}
~~~

When `@Transactional` is active (method invoked through a **Spring proxy**), and both template and manager use the same JMS `ConnectionFactory`, the sends can participate in the same local transaction. If the second send throws an exception that escapes the transaction boundary, the manager can roll back the sends belonging to that transaction.

Important limitations:

- **Self-invocation** within the same bean normally bypasses the `@Transactional` proxy.
- Using **different `ConnectionFactory` instances** in template and manager prevents sends from joining the intended transaction.
- Without an outer transaction, setting `JmsTemplate.sessionTransacted=true` usually creates a local transaction **per individual send/receive call**; it does not combine two calls into one transaction.
- A local JMS transaction does not atomically commit a database, Kafka, or HTTP call.

### Forwarding JMS → JMS inside the same transaction

In a flow receiving `orders.in`, validating synchronously, and sending to `orders.validated`, receive and send can share the same JMS transaction **when sharing the same resource and compatible thread/session transaction**:

~~~text
Receive orders.in (JMS transaction)
    -> validate synchronously
    -> Send orders.validated (same transaction when configured properly)
    -> commit

If handler throws an exception before commit:
    -> roll back JMS receive/send operations
    -> broker can redeliver the original request
~~~

Do not assume two endpoints sharing a `ConnectionFactory` automatically share a transaction if they run on different threads, separate connections/sessions, or different brokers. Verify against your chosen provider.

## 7. Distinguishing JMS transactions from database transactions

A flow receiving `OrderPaid` and updating PostgreSQL involves at least **two resources**:

1. **JMS transaction:** determines whether the broker treats the message as received or eligible for redelivery.
2. **Database transaction:** determines whether changes in PostgreSQL commit or roll back.

~~~mermaid
flowchart TD
    A["Receive JMS message evt-1001"] --> B["DB transaction BEGIN"]
    B --> C["Insert inbox key + update order"]
    C --> D["DB COMMIT"]
    D --> E{"JMS COMMIT succeeded?"}
    E -->|"Yes"| F["Complete"]
    E -->|"No"| G["Broker may redeliver"]
    G --> H["Receive evt-1001 again"]
    H --> I["Idempotency prevents duplicate side effect"]
~~~

`JmsTransactionManager` manages transactions on `ConnectionFactory`. `DataSourceTransactionManager` manages database transactions. Merely adding `@Transactional` or `sessionTransacted(true)` **does not create an atomic commit across both resources**. If distributed transactions are required, evaluate JTA/XA and real broker/database support; most systems adopt **at-least-once + inbox/outbox + idempotency**.

### 7.1. Idempotent consumer using a database unique key

Suppose a handler receives `OrderPaid(eventId=evt-1001, orderId=ORD-1001)`. You can create a `processed_event` table and insert into it **within the same DB transaction** as the business update:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customer_order (
    order_id VARCHAR(100) PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);
~~~

Example service using PostgreSQL and Spring JDBC:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaidProcessor {
    private final JdbcTemplate jdbc;

    public OrderPaidProcessor(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "orderDbTxManager")
    public void markPaid(String eventId, String orderId) {
        int inserted = jdbc.update(
                "INSERT INTO processed_event(event_id) VALUES (?) "
                + "ON CONFLICT DO NOTHING", eventId);

        if (inserted == 0) {
            return; // Event already processed; avoid duplicate write.
        }

        int updated = jdbc.update(
                "UPDATE customer_order SET status = 'PAID' "
                + "WHERE order_id = ?", orderId);

        if (updated != 1) {
            throw new IllegalStateException("Order does not exist: " + orderId);
        }
    }
}
~~~

`orderDbTxManager` must be a preconfigured database transaction manager bean, and this SQL **illustrates PostgreSQL only** (`ON CONFLICT DO NOTHING`); other databases have equivalent syntax. If the update throws an exception, **both the `processed_event` insert and the order update** roll back in the same DB transaction. If a JMS message is redelivered after DB commit, `inserted == 0` safely skips duplicate side effects.

The service must be called through a Spring proxy for `@Transactional` to take effect. Before invoking it, parse and validate JSON: non-empty `eventId`, valid `orderId`, supported `schemaVersion`. Use a stable `eventId` rather than `JMSMessageID` as the business idempotency key, because a producer may resend the same event with a new JMS message ID.

### 7.2. Critical failure windows

| Sequence | What can happen | How to handle |
|---|---|---|
| **DB commit → JVM crash → JMS commit did not happen** | Broker may redeliver an event already recorded in DB | Unique `eventId`/inbox prevents duplicate writes |
| **JMS ack/commit → async handler fails writing DB** | Broker may not redeliver because message was acknowledged | Avoid async split if JMS rollback protection is needed; or use durable handoff/dedicated retries |
| **DB commit → sending new JMS event fails** | Other systems miss the state change | Transactional outbox |
| **JMS send succeeds → outbox not yet marked sent** | Publisher may resend the same event | Idempotent consumer and stable event ID |

### 7.3. Transactional outbox for DB → JMS

~~~mermaid
flowchart LR
    A["Business service"] --> B["DB transaction: update order + insert outbox"]
    B --> C[("DB COMMIT")]
    C --> D["Outbox publisher"]
    D -->|"JMS outbound adapter"| E[("JMS broker")]
    D --> F["Mark SENT"]
~~~

Write business state and the event into an outbox table within the **same DB transaction**. A separate publisher reads unsent outbox rows and sends via JMS with retry/backoff. Marking an outbox row sent is **not atomic with broker commit** under standard single-resource transactions, so events may be sent more than once; consumers must remain idempotent.

## 8. `errorChannel` and exception propagation paths

Spring Integration's JMS message-driven adapter can wrap exceptions into an `ErrorMessage` sent to `errorChannel`. This is useful for logging, alerting, and error classification, yet **an error handled normally by an error flow can make the listener see the callback as successful**.

~~~mermaid
flowchart TD
    A["Transacted JMS session receives message"] --> B["Converter / handler"]
    B --> C{"Exception thrown?"}
    C -->|"No"| D["Listener ends -> JMS COMMIT"]
    C -->|"Yes"| E{"Does error escape to container?"}
    E -->|"Yes"| F["JMS ROLLBACK -> broker redelivery"]
    E -->|"No; absorbed by error flow"| G["Listener may COMMIT"]
~~~

Since Spring Integration 4.2, **conversion** errors in the JMS message-driven adapter/gateway can also route to the error channel. Hence placing `try/catch` solely inside business handlers **does not catch all errors**: failures can occur before a Spring Message reaches the handler.

| Error category | Recommended handling | Want JMS rollback? |
|---|---|---|
| DB timeout, transient dependency outage | Rethrow exception, bounded retry/backoff | Usually yes |
| Permanently malformed JSON, unknown `schemaVersion` | Quarantine/DLQ, alert, and data-fix process | Per policy; avoid infinite retry |
| Business rule rejection safely persisted | Finish handler with explicit business state | Possibly no |
| Duplicate event already committed earlier | Idempotent handler skips and returns success | No rollback needed |
| Failure on async thread after JMS committed | Independent retry/durable handoff | Cannot roll back original JMS |

**`errorChannel` is not a DLQ and does not retry JMS on its own.** To roll back, the exception must reach the **JMS transaction boundary**. To acknowledge an unprocessable message, explicitly ensure quarantine/error persistence succeeds before letting the callback complete normally.

### Do not swallow transient exceptions

~~~java
// Avoid this if you want broker redelivery on DB failure:
try {
    orderImportService.importOrder(json);
} catch (Exception ex) {
    log.error("Import failed", ex);
    // Callback finishes normally: listener may commit JMS.
}
~~~

On a synchronous path, when rollback is desired, let the exception propagate:

~~~java
try {
    orderImportService.importOrder(json);
} catch (org.springframework.dao.TransientDataAccessException ex) {
    log.warn("Temporary DB failure; allow JMS rollback", ex);
    throw ex;
}
~~~

These snippets illustrate handler code with `log` and a service already present; real error flows must also handle exceptions appropriately. Not every error warrants redelivery; policy should distinguish transient vs. permanent failures.

## 9. Redelivery, poison messages, and dead-letter queues

When a JMS transaction rolls back, the broker can **redeliver the message** per policy. JMS metadata provides `JMSRedelivered`; the `JMSXDeliveryCount` property can help observe delivery counts when supplied by the provider. Do not rely on every broker numbering, delaying, and dead-lettering identically.

~~~text
JMS receive -> exception -> rollback
                |
          broker redelivery
                |
       +--------+--------+
       |                 |
  Transient error    Permanent error
   (DB timeout)      (Bad JSON schema)
       |                 |
   Retry/backoff      Bounded retry
       |                 |
     Success         DLQ/quarantine
~~~

### 9.1. At-least-once is not exactly-once

With proper broker/provider, persistence, and transaction configuration, an application can **avoid losing messages on transient failures**, yet **the same message may arrive again**. That is **at-least-once delivery/processing attempt**. Inbox/idempotency is still required for **non-duplicate business effects**.

Never conclude `JMSRedelivered=false` means a business event has never arrived before: a producer can resend the same `eventId` in a brand-new JMS Message.

### 9.2. Poison messages

A permanently schema-invalid message can cause continuous listener rollbacks, clogging queues and flooding logs. Configure:

1. **Max delivery attempts** or retry threshold.
2. **Redelivery delay/backoff** to prevent tight spin loops.
3. **Dead-letter destination** once attempts exceed threshold.
4. Controlled remediation/replay workflows after verifying schema and idempotency.

DLQ names, retry policies, and expiry depend on the JMS broker. `orders.in.dlq` is only an illustrative name; brokers do not automatically invent this destination or move messages unless configured.

### 9.3. Logging and observability

Log/emit metrics when available for: `eventId`, JMS message ID, correlation ID, `JMSRedelivered`, delivery count if provided by the provider, queue name, exception type, processing duration, and transaction status. Never log secrets or raw payloads containing sensitive data.

## 10. Concurrency and asynchronous boundaries

### 10.1. Each consumer has its own session/transaction

`DefaultMessageListenerContainer` can run multiple consumers on a queue. For example, `concurrentConsumers=4` lets four listener tasks process four messages in parallel. One task rolling back **does not roll back other tasks' transactions**.

When multiple messages for the same order must be processed in sequence, raising concurrency can let `OrderUpdated(v2)` finish before `OrderCreated(v1)`. Use ordering/grouping strategies or `aggregateVersion` with optimistic locking in the DB.

### 10.2. `DirectChannel` preserves the synchronous boundary

~~~text
JMS receive (transacted)
    -> inbound adapter
    -> DirectChannel
    -> validate + DB service
    -> return / exception
    -> JMS commit / rollback
~~~

On a synchronous path, exceptions can still propagate back to the listener container to trigger JMS rollback.

### 10.3. `ExecutorChannel`/`QueueChannel` splits the transaction boundary

~~~text
JMS receive (transacted)
    -> inbound adapter
    -> ExecutorChannel / QueueChannel
    -> listener callback finishes -> JMS commit

        [another thread]
             |
         DB handler
             |
         exception (after JMS commit)
~~~

Successfully handing a Spring Message to an asynchronous channel **does not mean** the handler succeeded in writing to the DB. Errors occurring after the callback usually cannot roll back the original JMS message. If async processing is required, build a **durable handoff** (queue/work table/inbox/outbox) with dedicated retries; do not merely add an executor and assume the listener's transaction still protects downstream work.

## 11. JMS request-reply gateways and transactions

A JMS inbound gateway receives a JMS request, sends a Spring request into the flow, waits for a Spring reply, and sends a JMS reply back to `JMSReplyTo` or a fallback reply destination. With a transacted listener and synchronous processing, receiving and sending the reply can share the same JMS transaction when using compatible resources/sessions.

~~~mermaid
sequenceDiagram
    participant Client as JMS client
    participant Broker as Broker
    participant Server as Inbound gateway
    participant Handler as Spring handler
    Client->>Broker: Request + JMSReplyTo
    Broker->>Server: JMS request in listener session
    Server->>Handler: Spring request
    Handler-->>Server: Spring reply
    Server->>Broker: JMS reply
    Server->>Broker: JMS commit
    Broker-->>Client: Reply
~~~

A **business error reply** such as `NOT_FOUND` can be a valid JMS reply causing the transaction to commit. An **infrastructure exception** on DB failure or reply send failure can cause a rollback while the client sees a timeout. If `errorChannel` turns an exception into a Spring error reply and exits normally, the listener may treat the callback as successful; this is a deliberate business design choice.

A JMS outbound gateway is the side that **sends a request and waits for a reply**. If the caller times out, there is no proof the server did not process the request. For state-changing commands, retries must preserve a stable `requestId` and the server must be idempotent.

## 12. Design checklist and troubleshooting table

| Symptom | Causes to check | How to fix |
|---|---|---|
| DB fails but broker does not redeliver | `AUTO_ACK`, swallowed error, or async boundary | Use transacted listener / transactional poller and propagate exceptions |
| DB written yet message arrives again | JMS rollback/crash before commit; producer resend | Inbox / unique `eventId` |
| Polling adapter loses messages despite transacted template | Transaction committed right after `receive()` | Configure `JmsTransactionManager` on the poller |
| `ErrorMessage` logged while queue drains | Error flow absorbed exception | Rethrow if rollback is wanted; acknowledge intentionally only after quarantine |
| One schema-invalid message loops forever | Missing max attempts/DLQ | Backoff, bounded retries, DLQ, and poison-message handling |
| Enabling 4 consumers breaks order | Multiple sessions processing the same aggregate | Grouping/partitioning, versioning, or optimistic locking |
| JMS transaction works but DB duplicates | Two resources commit independently | Idempotent consumer/inbox |
| `@Transactional` has no effect | Self-invocation or wrong manager | Invoke via Spring proxy and specify transaction manager |
| Two JMS sends do not commit together | Not sharing the same local JMS transaction | Check manager, factory, and thread |
| Listener does not redeliver as expected | Container and acknowledgment mode differ from assumptions | Verify DMLC/SMLC, `sessionTransacted`, and provider policy |

Questions to answer before going to production: which destinations exist; do producer/consumer share schemas and `eventId`; who owns the JMS session; where do transactions end; are there any async channels; where do transient vs. permanent errors go; are redelivery/DLQ configured at broker or app; how do consumer/instance counts affect ordering; and which strategy keeps DB and JMS consistent.

## 13. Hands-on lab: from message loss to safe processing

**Environment:** test JMS broker, `orders.in` queue, Spring Integration, and PostgreSQL. Producer sends JSON `TextMessage`:

~~~json
{
  "eventId": "evt-1001",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "orderId": "ORD-1001"
}
~~~

Tests covering acknowledgment/redelivery must run against a real JMS provider or compatible test container. Mocking `JmsTemplate` cannot prove the broker persisted, rolled back, or moved messages to a DLQ.

### Lab A — Comparing acknowledgment modes

1. Create a DMLC using `AUTO_ACKNOWLEDGE`, `sessionTransacted=false`. Have the handler throw an exception after receiving.
2. Observe queue depth and whether the broker redelivers; do not guess merely from the handler throwing.
3. Switch to `CLIENT_ACKNOWLEDGE` and compare best-effort redelivery when the listener fails.
4. Enable `sessionTransacted=true`; throw synchronously and observe broker rollback/redelivery.
5. Resend a new JMS message with the same `eventId`; verify the difference between JMS redelivery and producer duplicates.

### Lab B — Transactional poller

1. Create a polling adapter with `sessionTransacted=true` only on the receiving template, and have the handler throw an exception.
2. Explain why `receive()` could already have committed before the handler failed.
3. Switch to a transactional poller with `JmsTransactionManager`, keeping `DirectChannel`.
4. Repeat the failure and observe broker redelivery.
5. Insert an `ExecutorChannel` and verify whether downstream failures can still roll back the poller.

### Lab C — JMS + DB and idempotency

1. Create `processed_event` and `customer_order` tables.
2. Have the handler update the order and insert `eventId` in the same DB transaction.
3. Simulate a DB commit followed by a failure before JMS commit.
4. When the broker redelivers, verify no duplicate business side effects occur.
5. Resend the event via a new JMS Message carrying the same `eventId` and repeat verification.

### Lab D — Poison messages and DLQ

1. Send invalid JSON or an unsupported `schemaVersion`.
2. With a transacted listener, observe rollback and redelivery.
3. Configure an error channel that logs without rethrowing; compare how the listener commits.
4. Test exception propagation, bounded retries/backoff, and DLQ routing per broker policy.
5. Fix the payload and replay safely; confirm idempotency still holds.

### Lab E — Outbound JMS transactions

1. Configure `JmsEventPublisher.publishPair(...)` with `@Transactional(transactionManager="orderJmsTxManager")`.
2. Make the second send throw an exception and verify both roll back in the same JMS transaction.
3. Compare calling the service through a Spring proxy vs. self-invocation.
4. Add a DB update in another method and explain why a local JMS transaction is not atomic with the DB.
5. Design an outbox so events can be retried after DB commit.

### Self-check questions

1. Distinguish **JMS acknowledge** from **database commit**.
2. Why does `AUTO_ACK` on DMLC not guarantee redelivery when a handler fails?
3. Under `CLIENT_ACK`, does `Message.acknowledge()` confirm only the current message or potentially multiple messages received on the session?
4. When a session is transacted, which operations control JMS commit/rollback?
5. Why can a Spring Integration message-driven adapter and a manually constructed DMLC have different defaults?
6. Why does setting `sessionTransacted=true` only on `JmsTemplate` inside a polling adapter fail to protect downstream handlers?
7. Under what conditions does `JmsTransactionManager` span two JMS sends?
8. When DB commit succeeds but JMS rolls back, what mechanism prevents duplicate writes?
9. How can an error flow that swallows exceptions affect a transaction?
10. How does `ExecutorChannel` change the transaction boundary of JMS inbound?
11. Why does `JMSRedelivered` not replace `eventId`?
12. How should permanently schema-invalid messages be handled to avoid retry storms?

## 14. References

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): polling inbound transactions, message-driven adapter transacted default, error channels, and conversion errors.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): listener containers, acknowledge modes, transaction management, and `JmsTemplate`.
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): lifecycle, acknowledge mode, concurrency, and `sessionTransacted`.
- [Spring Framework API — JmsTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html): local JMS transactions bound to `ConnectionFactory`.
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): transaction advice, pollers, and transaction boundaries in integration flows.

**Remember:** acknowledgment determines **whether the broker considers a receive finished**, while a JMS transaction lets related session operations commit/roll back together. In Spring Integration, place transactions at the **right endpoint and synchronous boundary**: transacted listeners for message-driven, transactional pollers for polling, and `JmsTransactionManager` for JMS operations that must share a transaction. Because JMS transactions are not automatically atomic with databases, real reliability also depends on idempotency, inbox/outbox, bounded retries, and DLQs.

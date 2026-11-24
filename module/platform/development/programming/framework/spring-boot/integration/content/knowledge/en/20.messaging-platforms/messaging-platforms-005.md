# Confirming Sent, Broker Received, and Consumer Processed

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot organizes integrations via HTTP clients, databases, caches, message brokers, and Spring Integration adapters. An order flow might update PostgreSQL, publish an event to Kafka/RabbitMQ, and let another consumer sync reports or send notifications. Along that flow, three questions are easily conflated:

- **Has the producer sent it?** Has the send API call merely been initiated, buffered, or received a final producer outcome?
- **Has the broker received it?** Under what guarantee level did the broker confirm, did the record reach the target topic/queue, and will it survive a crash?
- **Has the consumer processed it?** Has the consumer only received the message, or has it committed its business transaction and recorded the ACK/offset?

A `send()` call without an exception **does not prove** the consumer finished its business work. Even a broker ACK confirm does not indicate the report has been updated. Conversely, a consumer may have committed its database yet lost connection before ACKing and be forced to receive the same event again.

This lesson belongs to the **Messaging Platforms** chapter, focusing on **Confirming Sent, Broker Received, and Consumer Processed**. It brings together Kafka, RabbitMQ/AMQP, and JMS with data contracts, transactions, errors, duplicate handling, testing, and observability in practice.

After this lesson, you will be able to:

1. Distinguish send invoked, producer completion, broker acknowledgement, consumer delivery, business commit, and consumer ACK/offset commit.
2. Explain `KafkaTemplate.send(...)` results and the effects of `acks`, idempotent producers, and group offsets.
3. Explain RabbitMQ publisher confirms, mandatory returns, consumer `basic.ack`/`basic.nack`, and prefetch.
4. Identify JMS transaction/acknowledgement modes.
5. Design durable outboxes/inboxes and stable business idempotency keys.
6. Analyze failure windows when one party commits while the other has not recorded an ACK.
7. Write integration tests for retries, crash/replay, DLQ, and broker outages.
8. Measure distinct metrics for broker confirmed, consumer delivered, and business applied.

> **Principle:** You must state explicitly **who acknowledges, what is being acknowledged, at what moment, and within which transaction scope**. Simply logging “message succeeded” in logs or dashboards is insufficient.

## 1. Milestones of a Message

~~~mermaid
sequenceDiagram
    participant P as Producer Service
    participant DB as Producer Database
    participant B as Broker
    participant C as Consumer
    participant R as Consumer Database
    P->>DB: Commit business state + outbox intent
    P->>B: Send event
    B-->>P: Publisher/broker ACK
    B->>C: Deliver record/message
    C->>R: BEGIN + apply event + inbox
    R-->>C: COMMIT
    C-->>B: Consumer ACK / commit offset
    Note over P,C: Publisher ACK and Consumer ACK are not the same
~~~

| Milestone | Evidence Issuer | What Can Be Concluded | What Cannot Be Concluded |
| --- | --- | --- | --- |
| **Intent committed** | Producer database | Intent to emit the event is durably saved | Event is at the broker |
| **Send invoked** | Producer app | Send was called/queued on the client | Broker received it |
| **Producer send completed** | Producer client callback/future | Completed per producer configuration | Consumer processed it |
| **Broker accepted** | Kafka broker or Rabbit publisher confirm | Broker acknowledged per its rules | All downstream consumers processed the message |
| **Consumer delivered** | Kafka poll/AMQP delivery | Consumer received access to the message | Handler committed |
| **Business committed** | Consumer DB/service | Side effect completed within confirmed scope | Broker ACK succeeded |
| **Consumer acknowledged** | Consumer→broker | Broker recorded progress/settlement | Another SQL transaction definitely succeeded |

In Kafka, consumer progress is stored via the group's **offset commit**; records remain retained per retention/compaction. In RabbitMQ, a consumer ACK typically settles a delivery and lets the broker remove it from the queue. These two mechanisms are **different** even though both are casually called “ack.”

### 1.1. Statuses Must Be Named Accurately

Use explicit statuses such as:

~~~text
OUTBOX_PENDING
  -> PRODUCER_IN_FLIGHT
  -> BROKER_CONFIRMED

CONSUMER_DELIVERED
  -> BUSINESS_APPLIED
  -> CONSUMER_ACKNOWLEDGED

CONSUMER_DELIVERED
  -> RETRY_PENDING
  -> PARKED_IN_DLQ
~~~

These are **statuses or events belonging to two different systems**; a single table does not necessarily see all of them. The producer does not automatically know when the consumer committed; if needed, design completion events, a status API, a shared audit store, or reconciliation.

### 1.2. Why Is “Sent” Easily Misunderstood?

~~~text
t0    Service calls KafkaTemplate.send()
t1    Method returns CompletableFuture
t2    Kafka client buffers the record
t3    Broker appends/replicates per acks policy
t4    Producer future completes normally
t5    Consumer poll() fetches the record
t6    Business SQL transaction commits
t7    Consumer commits offset
t8    Reporting UI displays the result
~~~

At `t1` you cannot claim it reached the broker. At `t4` you cannot claim it was processed. At `t6` the consumer offset may not be committed yet. And at `t7` all other caches/views may not yet be updated.

## 2. Delivery Semantics: At-Most-Once, At-Least-Once, Exactly-Once

| Semantics | Meaning | Trade-Off |
| --- | --- | --- |
| **At-most-once** | Each message executes at most once, but may be lost | Simple, but does not guarantee completion |
| **At-least-once** | Message is retried until success is recorded per policy | Consumer must prevent duplicate side effects |
| **Scoped exactly-once** | An outcome commits once within specific technology boundaries | Does not automatically extend to SQL, HTTP, Redis, or other brokers |

For instance, Kafka's idempotent producer reduces duplicates caused by **producer retries within one producer session** using corresponding sequences. Kafka transactions can coordinate output records and consumer offsets within Kafka when doing **Kafka → Kafka** processing. Yet a Kafka transaction does not turn PostgreSQL's `INSERT INTO orders` and an HTTP POST to an ERP into one atomic transaction.

**The idempotency key must be a stable business identity**, such as `eventId`/`operationId` preserved across replays—not a trace ID, Kafka offset, Rabbit delivery tag, or Spring Message ID.

## 3. Kafka Producer: Send and ACK Settings

Spring Kafka provides `KafkaTemplate<K,V>`. On Spring Kafka 3.x, `send(...)` returns `CompletableFuture<SendResult<K,V>>`:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderEvent>>
            publish(OrderEvent event) {

        return kafkaTemplate.send(
                "orders.events",
                event.orderId(),
                event);
    }
}
~~~

`OrderEvent` is an application contract DTO/record detailed in section 11. The producer requires appropriate serializer/topic/security settings.

**Conclusions by milestone:**

- `send(...)` called and returns a future: **does not prove broker receipt**.
- Future completes normally: send finished **per producer `acks` config**.
- `SendResult.getRecordMetadata()`: provides topic/partition/offset for Kafka reconciliation, **not consumer processing outcome**.
- Future completes exceptionally: a producer error occurred, yet if the ACK was lost after the broker appended, **you cannot be sure the message does not exist**.

### 3.1. A Properly Semantic Callback

~~~java
public void publishWithCallback(OrderEvent event) {

    kafkaTemplate
            .send("orders.events", event.orderId(), event)
            .whenComplete((result, failure) -> {
                if (failure != null) {
                    // Record attempt error / unknown for retry and reconciliation.
                    // Do not conclude the broker definitely did not receive it.
                    recordPublishFailure(event.eventId(), failure);
                    return;
                }

                var metadata = result.getRecordMetadata();

                // This is only producer/broker completion.
                recordBrokerConfirmed(
                        event.eventId(),
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset());
            });
}
~~~

`recordPublishFailure` and `recordBrokerConfirmed` are illustrative hooks. The asynchronous callback may fire after the HTTP response has returned; a process crash right after broker ACK but before DB status update can trigger retries and duplicates. Never set a business status like `CONSUMER_PROCESSED` from a producer callback.

### 3.2. acks=0, acks=1, acks=all

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
~~~

| Setting | Condition Under Which Producer Treats Send as Success | Meaning for Durability |
| --- | --- | --- |
| `acks=0` | Producer does not wait for broker confirmation | Very easy to lose proof of broker receipt |
| `acks=1` | Leader broker confirms | Can lose records if the leader fails before replicas catch up |
| `acks=all` or `acks=-1` | Leader waits for sufficient acknowledgements per ISR/policy | Depends on replication factor, `min.insync.replicas`, and cluster health |
| `enable.idempotence=true` | Uses producer sequences to limit duplicates from internal retries | Does not prevent business events republished from a fresh outbox run |
| `delivery.timeout.ms` | Producer deadline for delivery | Timeout does not mean the request never reached the broker |
| `max.in.flight.requests.per.connection` | In-flight request limit | Must align with ordering/idempotence policy |

**Do not interpret `acks=all` as “every broker in the cluster persisted it forever.”** It depends on active ISR, topic settings, replica count, min ISR, and storage integrity. On a single-replica cluster, `acks=all` still provides no HA.

### 3.3. A Lost ACK Can Cause Duplicates

~~~mermaid
sequenceDiagram
    participant P as Kafka Producer
    participant K as Kafka Broker
    P->>K: Produce eventId=E-100
    K->>K: Append record
    K--xP: ACK lost / network interruption
    P->>P: Timeout / unknown outcome
    P->>K: Retry eventId=E-100
    Note over P,K: Broker or consumer may see duplicates
~~~

Producer idempotence handles certain producer-retry windows, yet if the application emits **another record after restart**, the consumer must still deduplicate by `eventId` if the business cannot apply it twice.

### 3.4. Producer ACK Does Not Measure Consumer Lag

`RecordMetadata` holds the record's offset in a partition. Consumers may not be subscribed yet, may be replaying old data, rebalancing, or failing DB transactions after reading. Dashboards should separate **producer confirmation** and **consumer business outcome** into distinct sections.

## 4. Kafka Consumer: Receiving Records and Committing Offsets

~~~mermaid
sequenceDiagram
    participant K as Kafka Broker
    participant C as Consumer
    participant D as Reporting DB
    K->>C: Poll event offset=1042
    C->>D: BEGIN + update projection + inbox
    D-->>C: COMMIT OK
    C->>K: Commit offset=1043
    Note over C,K: ACK/offset commit can fail after DB COMMIT
~~~

Kafka concepts:

- **Record offset:** position of a record within a partition.
- **Consumer position:** next position an active consumer will fetch.
- **Committed offset:** durably saved progress for a consumer group.
- **Consumer lag:** difference between log end offset and current progress as measured.

Zero lag does not prove messages were properly business-committed: offsets might have been committed too early, handlers might have dropped records erroneously, or updates might live only in RAM.

### 4.1. Spring Kafka Manual Acknowledgment

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual_immediate
~~~

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    private final OrderProjectionService service;

    public OrderProjectionListener(
            OrderProjectionService service) {
        this.service = service;
    }

    @KafkaListener(
            topics = "orders.events",
            groupId = "reporting-projection")
    public void consume(
            OrderEvent event,
            Acknowledgment acknowledgment) {

        service.applyIdempotently(event);

        // ACK only after the service has committed successfully.
        acknowledgment.acknowledge();
    }
}
~~~

`OrderProjectionService` must genuinely open a transaction and finish committing before returning. The container must be configured for manual acknowledgment; this example targets a synchronous Kafka listener. If the service merely spawns a `CompletableFuture` or submits to an executor and returns, ACKing right afterward **can lose messages** on process crash.

### 4.2. Failure Window: ACK Before Database Commit

~~~text
Record delivered
    |
    +-- Commit Kafka offset
    |
    +-- SQL UPDATE
          |
          +-- Process crash / SQL rollback
~~~

The consumer group advances from the new offset; the unapplied record will not reappear under normal consumption. This creates an unintended **at-most-once business effect**.

### 4.3. Failure Window: Database Commit Before Offset ACK

~~~text
Record delivered
    |
    +-- SQL COMMIT succeeds
    |
    +-- Process crashes before offset commit
    |
    +-- Redelivery of same eventId
~~~

This is normal under at-least-once. You need an **idempotent consumer**: insert the inbox marker and business update in the same database transaction so replays create no extra side effects.

### 4.4. Rebalances, Partitions, and Ordering

A Kafka consumer group distributes partitions across instances. During a rebalance, records without committed progress can reappear. Never use an in-memory `Set<eventId>` for deduplication because new instances lack that history.

Kafka ordering applies **per partition**, with no global order across partitions. If events for an order must be processed in version order, use `orderId` as the Kafka message key and check `aggregateVersion` in the database. Partitioning aids ordering, but does not replace a business version guard.

## 5. RabbitMQ Publisher: Confirms and Returns Are Two Different Things

A RabbitMQ publisher sends messages to an **exchange**, which routes them to one or more queues per binding/routing keys.

~~~mermaid
flowchart LR
    P["RabbitTemplate publisher"] --> E["Exchange"]
    E -->|"Binding match"| Q["Queue"]
    E -->|"No binding"| U["Unroutable"]
    E -. "Publisher confirm ACK" .-> P
    U -. "Return if mandatory" .-> P
    Q --> C["Consumer"]
    C -. "basic.ack / basic.nack" .-> Q
~~~

Publisher confirms verify the broker handled the publish per RabbitMQ mechanics. However, if **no matching binding exists**, a message can still receive a confirm ACK without landing in any expected queue. To detect routing failures, enable `mandatory` and handle publisher returns per policy.

### 5.1. Configuring Correlated Confirms and Returns

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
}
~~~

~~~yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Credentials must come from environment secret sources. `publisher-confirm-type=correlated` links confirms to specific publish calls. `publisher-returns=true` combined with `mandatory=true` notifies you of unroutable messages per broker semantics.

### 5.2. CorrelationData and Confirm Callback

~~~java
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class RabbitOrderPublisher {

    private final RabbitTemplate rabbitTemplate;

    public RabbitOrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(OrderEvent event) {
        CorrelationData data =
                new CorrelationData(event.eventId());

        rabbitTemplate.convertAndSend(
                "orders.exchange",
                "order.confirmed",
                event,
                data);

        data.getFuture().whenComplete((confirm, failure) -> {
            if (failure != null) {
                recordPublishError(event.eventId(), failure);
                return;
            }

            if (!confirm.isAck()) {
                recordNack(event.eventId(), confirm.getReason());
                return;
            }

            // Broker confirmed; inspect returns/routing separately.
            recordConfirmAndReturn(
                    event.eventId(), data.getReturned());
        });
    }
}
~~~

`recordPublishError`/`recordNack`/`recordConfirmAndReturn` are application-specific methods. `getFuture()` and `getReturned()` belong to modern Spring AMQP—verify against your version; message converters and exchanges must be configured properly.

**Note:** `RabbitTemplate.convertAndSend(...)` not throwing only means the client publish call did not fail immediately. The confirm callback does **not** prove the consumer processed the message. If an outbox needs routing verification, store and classify returned messages in addition to confirms.

### 5.3. RabbitMQ Durability Is More Than Confirms

Relevant factors:

- Durable exchange/queue topology.
- Persistent message delivery mode where required.
- Queue type (classic/quorum), replication/failover.
- Publisher confirms and publisher returns.
- Message TTL, queue expiration, dead-letter settings.
- Broker disk/memory alarms, storage reliability, and policies.

A confirmed message can still expire, be misrouted, be consumed and ACKed, or be dropped by lifecycle policies. Do not equate **publisher-confirmed** with “the message will stay in the queue forever.”

## 6. RabbitMQ Consumer ACK: Taking Ownership After Processing

AMQP operations:

| API | Meaning |
| --- | --- |
| `basic.ack(deliveryTag, false)` | ACK one specific delivery |
| `basic.ack(deliveryTag, true)` | ACK all unacked deliveries up to delivery tag on the channel |
| `basic.nack(tag, false, true)` | Reject and requeue per broker policy |
| `basic.nack(tag, false, false)` | Reject without requeuing; may dead-letter if configured |
| `basic.reject(tag, requeue)` | Reject one message |
| `basic.qos(prefetch)` | Cap unacked deliveries within the applicable scope |

Manual consumer ack in Spring AMQP:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: manual
        prefetch: 10
~~~

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderRabbitConsumer {

    private final OrderProjectionService service;

    public OrderRabbitConsumer(
            OrderProjectionService service) {
        this.service = service;
    }

    @RabbitListener(queues = "orders.reporting")
    public void consume(
            OrderEvent event,
            Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG)
            long deliveryTag) throws IOException {

        service.applyIdempotently(event);

        channel.basicAck(deliveryTag, false);
    }
}
~~~

This assumes a message converter maps the body to `OrderEvent`, along with an appropriate Rabbit listener container and error handling. If `service.applyIdempotently` throws, the handler needs a clear requeue/retry/DLQ policy. Never assume throwing in manual mode automatically ACKs/NACKs as desired.

### 6.1. Why Is Early ACK Dangerous?

~~~text
Broker delivers message
  -> Handler pushes work into in-memory executor
  -> basic.ack() immediately
  -> Worker process crashes
  -> Work in RAM lost
~~~

The broker removed the delivery from the queue before any durable effect occurred. For asynchronous processing, **handoff must be durably stored** (work table/outbox or another durable broker) before ACKing the source.

### 6.2. Continuous Requeue Causes a Retry Storm

If a message violates schema and the consumer always calls `basic.nack(requeue=true)`, RabbitMQ can redeliver immediately, spiking CPU/logs and starving valid messages. For permanent errors, route to a DLQ/parking store per policy; for transient errors, use bounded delayed retries/backoff.

**DLQ handoff also needs confirmation:** if a consumer manually publishes to a DLQ and ACKs the original message before the broker confirms the DLQ publish, a crash can lose the message from both places. Broker dead-lettering behaves differently across queue types; test actual semantics.

### 6.3. Prefetch and Concurrency

Prefetch caps unacked deliveries; it does not automatically create parallelism. Concurrency depends on the listener container, executors, database pool, and handler throughput. Overly large prefetch inflates in-flight messages, crash redelivery bursts, and memory pressure.

## 7. JMS Acknowledgements and Spring Transactions

JMS also separates send, provider receipt, consumer delivery, and application processing, though its APIs differ from Kafka/RabbitMQ.

| JMS Mode | Meaning | Limitation |
| --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | Provider/container ACKs per receive/listener lifecycle | Does not combine with SQL transactions by default |
| `CLIENT_ACKNOWLEDGE` | Client explicitly calls `Message.acknowledge()` | May ACK multiple messages received on the same session |
| `DUPS_OK_ACKNOWLEDGE` | Permits lazy acknowledgements | Duplicates may appear |
| `SESSION_TRANSACTED` | Local JMS session commit/rollback | Not automatically atomic with JDBC |
| XA/JTA | Coordinates resource managers under configured distributed transactions | Operational cost/complexity; both broker and DB must support it |

`JmsTemplate.send(...)` completing does not prove listeners finished business work. `@JmsListener` follows the listener container's acknowledgement and transaction configuration.

A `@Transactional` using `DataSourceTransactionManager` does not automatically enlist a JMS session or Kafka offset in the same database transaction. Specify the right transaction manager, or use outbox/inbox when not adopting XA/JTA.

## 8. Three-Platform Comparison Table

| Question | Kafka | RabbitMQ | JMS |
| --- | --- | --- | --- |
| Producer completion | Send future/callback per `acks` | Publisher confirm (if enabled) | Per JMS provider/send semantics |
| Routing | Topic/partition key | Exchange, binding, routing key → queue | Provider destination |
| Consumer progress | Consumer group offset commit | Consumer `basic.ack`/`nack` | Session acknowledgement/transaction |
| Does message remain after consumption? | Kafka log per retention/compaction | Queue messages are normally settled/removed after ACK | Per provider/destination |
| Redelivery on crash? | Yes if offset wasn't committed | Yes if delivery wasn't ACKed or was requeued | Yes per mode/provider |
| Producer ACK = consumer processed? | **No** | **No** | **No** |
| Consumer ACK atomic with SQL? | **Not by default** | **Not by default** | **Not by default** |
| Dead-letter support | DLT topic/app policy | DLX/DLQ topology | Provider/application policy |

When instrumenting telemetry, use specific names like `kafka.producer.acked`, `rabbitmq.publisher.confirmed`, `rabbitmq.consumer.acked`, `kafka.consumer.offset.committed`, and `business.event.applied`. Avoid a single generic `messages.success` counter spanning every layer.

## 9. Transactional Outbox: Recording Publish Intent Alongside Business State

Anti-pattern:

~~~java
@Transactional
public void confirmOrder(String orderId) {
    orderRepository.markConfirmed(orderId);
    kafkaTemplate.send(
            "orders.events",
            orderId,
            new OrderConfirmed(orderId));
}
~~~

With async Kafka, calling `send(...)` inside a JDBC transaction **does not** form a shared transaction. The event may publish even if SQL rolls back, or SQL may commit while publishing fails. Establish explicit transaction boundaries.

### 9.1. Outbox Flow

~~~mermaid
flowchart LR
    A["Order command"] --> B["SQL transaction"]
    B --> C["Update order"]
    B --> D["Insert outbox event"]
    D --> E["Relay / CDC / worker"]
    E --> F["Kafka/RabbitMQ/JMS"]
    F --> G["Consumer"]
    G --> H["Inbox + business update"]
    E -.-> I["Retry + monitor broker confirms"]
~~~

Within the **same SQL transaction**, update the order and insert an outbox row holding a unique `eventId`, payload contract, and PENDING status. Once committed, the system owns preserving publish intent; a relay reads the outbox to send, records broker outcomes, and retries when needed.

### 9.2. Illustrative PostgreSQL Schema

~~~sql
CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    schema_version INT NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    broker_confirmed_at TIMESTAMPTZ NULL
);

CREATE INDEX idx_outbox_due
ON integration_outbox(status, next_attempt_at, created_at);
~~~

`event_id` must never change across republications; otherwise the consumer inbox cannot recognize a replayed intent. Plan storage/access controls for payloads containing PII and compliant archive/delete lifecycles.

### 9.3. Publisher Confirms Do Not Yield End-to-End Exactly-Once

~~~mermaid
sequenceDiagram
    participant R as Outbox Relay
    participant B as Broker
    participant D as SQL Outbox
    R->>B: Publish eventId=E-100
    B-->>R: Broker confirmed ACK
    R->>D: Update BROKER_CONFIRMED
    Note over R,D: Process crashes before SQL commit
    R->>B: Retry E-100 on restart
    Note over R,B: Duplicate record may occur
~~~

Outboxes typically provide **at-least-once publication**. If the broker ACKs and the process crashes before writing `BROKER_CONFIRMED`, retrying avoids losing the event. Consumers must tolerate duplicates.

### 9.4. Claiming Outbox Rows Across Multiple Workers

In PostgreSQL, `FOR UPDATE SKIP LOCKED` lets multiple workers pick non-overlapping rows **while row locks are held inside a transaction**.

~~~sql
SELECT event_id, payload
FROM integration_outbox
WHERE status = 'PENDING'
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

This only selects rows inside the transaction; once the transaction ends, locks release. If publishing occurs outside the transaction, design durable **status/lease owners, expirations, and reclamation**; do not assume `SELECT ... SKIP LOCKED` keeps rows locked during the broker send.

## 10. Consumer Inbox: Executing Side Effects Once per eventId

Consumers use a reliable business event key such as `eventId` to check prior processing:

~~~sql
CREATE TABLE processed_integration_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Each consumer has its own business responsibility, so the key combines `consumer_name + event_id` to allow different consumers to validly process the same event.

### 10.1. Idempotent PostgreSQL Transaction

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbcTemplate;

    public OrderProjectionService(
            JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void applyIdempotently(OrderEvent event) {

        int inserted = jdbcTemplate.update(
                """
                INSERT INTO processed_integration_events(
                    consumer_name, event_id, processed_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (consumer_name, event_id)
                DO NOTHING
                """,
                "reporting-projection",
                UUID.fromString(event.eventId()));

        if (inserted == 0) {
            return; // Duplicate; business side effect already applied.
        }

        jdbcTemplate.update(
                """
                INSERT INTO reporting_orders(order_id, state)
                VALUES (?, ?)
                ON CONFLICT (order_id)
                DO UPDATE SET state = EXCLUDED.state
                """,
                event.orderId(),
                event.state());
    }
}
~~~

`reporting_orders` must be created via migrations. The example assumes `event.eventId()` is a valid UUID string and the service method is invoked through a Spring `@Transactional` proxy using the proper transaction manager. `INSERT inbox` and `UPDATE/INSERT business` must commit **in the same SQL transaction**. If the update fails, the inbox insert must roll back too so the event is not falsely marked processed without business application.

**Ordering note:** deduplicating `eventId` does not stop an older event version from overwriting a newer one. For versioned aggregates, repositories must condition updates on higher/sequential versions.

### 10.2. External Side Effects Outside the SQL Transaction

If a consumer writes to the inbox and then sends HTTP/SMTP, whether the remote HTTP call succeeded does not roll back with PostgreSQL. You can persist the inbox marker plus a **follow-up outbox row** in one transaction, then let a dedicated adapter send HTTP with a stable operationId and reconciliation.

Never cite a SQL inbox to claim a remote ERP payment executed exactly once if the remote API lacks idempotency/lookup support.

## 11. Schemas and Message Contracts

Example event:

~~~java
public record OrderEvent(
        String eventId,
        String orderId,
        long aggregateVersion,
        String eventType,
        int schemaVersion,
        String state,
        String occurredAt) {
}
~~~

| Property | Purpose |
| --- | --- |
| `eventId` | Deduplication key across retries/redeliveries |
| `orderId` | Business key and Kafka partition key |
| `aggregateVersion` | Blocks stale events from overwriting newer state |
| `eventType` | Classifies message/handler |
| `schemaVersion` | Evolves serializer contracts |
| `state` | Business state |
| `occurredAt` | Audit; does not replace idempotency keys |
| `traceId` (header) | Links observability for a single attempt |

When retrying publication of **the same intent**, keep `eventId` and business fields unchanged. Broker metadata like Kafka offsets, RabbitMQ delivery tags, and Spring `Message.id` can vary per delivery and make poor deduplication keys.

Schema Registry, JSON Schema, Avro, or Protobuf can enforce schema evolution, yet a broker ACK does not mean the payload passed business validation or was authorized for a tenant.

## 12. Failure Windows in Sequence

| Failure Window | Consequence | Design Direction |
| --- | --- | --- |
| SQL commits before publish, process crashes | Publish intent may be lost | Outbox |
| Publish before SQL commit, SQL rolls back | Consumers see non-existent events | Outbox in same SQL transaction |
| Broker appends, producer misses ACK | Producer times out, may resend | Stable eventId, idempotent producer, consumer inbox |
| Rabbit confirms ACK, fails to route | No queue receives it | Mandatory returns and binding tests |
| Producer confirms before outbox state update, crashes | Duplicate publish on replay | Consumer idempotency |
| Consumer ACKs before SQL commit, crashes | Lost business effect | ACK after commit |
| Consumer SQL commits before ACK, crashes | Redelivery and duplicate attempt | Inbox / unique constraint |
| Consumer hands off to RAM then ACKs | Pending work lost on restart | Durable handoff |
| Permanent/schema error requeued endlessly | Retry storm, backlog | DLQ/parking/rejection store |
| DLT publish unconfirmed yet source ACKed | Message can be lost completely | Durable DLQ handoff |
| Consumer applies older event after newer event | State regresses | AggregateVersion / partition ordering |

### 12.1. DB Commit Before Consumer ACK Is Expected

Under at-least-once, consumers **deliberately** allow redelivery if ACKing fails, because ACKing before business commit risks losing effects. Hence business consumers must be idempotent. “Consumer received duplicates” is not inherently a broker bug.

### 12.2. ACKing a Failing Message Can Also Be Correct

If a message fails schema validation, the consumer must not retry infinitely. After **recording a rejection or durably moving it to a DLQ**, policy may ACK the source message to prevent a poison message from blocking the queue. Its business status remains `REJECTED`/`PARKED`, never `SUCCESS`.

## 13. Retries, Dead-Lettering, and Concurrency

### 13.1. Error Classification

| Category | Example | Policy |
| --- | --- | --- |
| Bad schema / invalid payload | Missing required field, unknown contract | Do not retry indefinitely; reject/DLQ |
| Broker temporarily unavailable | Connect/rebalance/broker outage | Retry with backoff and budget |
| Database deadlock/timeout | Transient SQL failure | Retry transaction/item with idempotency |
| Authorization failure | Bad ACL/credentials | Fix config, alert |
| Downstream HTTP 503 | Partner overload | Bounded retry, circuit breaker |
| Downstream request timeout after write | Outcome unknown | Status lookup/idempotency/reconciliation |
| Duplicate event ID | Already in inbox | Do not reapply; safe to ACK |

Avoid accidentally layering 3 producer retries, 3 listener retries, 3 HTTP client retries, and 3 scheduler retries. Total attempts multiply rapidly and overload downstream services. Pick one primary retry boundary and enforce a budget.

### 13.2. Dead-Letter Does Not Equal Business Completion

Kafka DLT or RabbitMQ DLQ holds unprocessable events for investigation and replay. A message reaching the DLT proves it was **parked** by the workflow, not that downstream business processing succeeded. Dashboards must never count DLT totals inside `business_applied`.

### 13.3. Concurrency and Ordering

Kafka: partition keys preserve per-key/partition order, though replays can still occur; use version guards.

RabbitMQ: prefetch and listener concurrency control in-flight deliveries without guaranteeing completion order.

JMS: destination/provider concurrency and session transactions shape ordering/ack semantics.

Never treat message “received” timestamps as proof that effects “committed” if handlers run async on worker threads.

## 14. Layered Observability

| Metric | What It Measures | What It Does Not Prove |
| --- | --- | --- |
| `integration.outbox.created` | Committed publish intents | Broker received them |
| `integration.producer.attempts` | Send attempts | Success |
| `integration.producer.confirmed` | Broker confirmations per policy | Consumer processed them |
| `integration.producer.returned` | Rabbit publisher returns/unroutable | Consumer processed them |
| `integration.consumer.deliveries` | Messages delivered to consumer | DB committed |
| `integration.consumer.business_applied` | Side effects committed cleanly | Consumer offset committed |
| `integration.consumer.duplicates` | Inbox deduplications | Data was always valid |
| `integration.consumer.ack_errors` | ACK/offset progress write errors | Business failed |
| `integration.consumer.dlq` | Parked messages | Business success |
| `integration.end_to_end.lag` | Delay from intent to business outcome | Each individual phase |

A consistent example:

~~~text
Producer broker-confirmed events: 100
Consumer deliveries:            104
Unique business applied:        98
Duplicate deliveries:            4
Parked in DLQ:                   2
~~~

These numbers are consistent because broker/consumer use **at-least-once**, while two unprocessable events sit in the DLQ. Never report “100/100 business success” just from `producer confirmed=100`.

### 14.1. Latency Categories

- **Producer acknowledgement latency:** send call to producer callback/future completion.
- **Broker/consumer lag:** time a record waits in the broker before consumer processing.
- **Business processing latency:** handler start to business transaction commit.
- **ACK/offset commit latency:** recording progress after processing.
- **End-to-end business latency:** producer intent commit to downstream business effect completion.

A very low producer p95 can still accompany hours-long consumer lag if consumers crash or databases stall. Investigate using ingress rate, broker backlog, DB pools, and business handlers together.

### 14.2. Micrometer Observation for Business Processing

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public void observedApply(
        ObservationRegistry registry,
        OrderProjectionService service,
        OrderEvent event) {

    Observation.createNotStarted(
                    "integration.order.consumer.apply", registry)
            .lowCardinalityKeyValue(
                    "consumer", "reporting-projection")
            .observe(() ->
                    service.applyIdempotently(event));
}
~~~

Observation times the synchronous call; if the `@Transactional` method is proxied and commits on method return, the timer includes commit time per instrumentation. It does not measure Kafka offset commit here because `acknowledge()` has not been called inside this method.

Keep tags bounded, e.g., `broker=kafka`, `topic=orders.events`, `outcome=applied/duplicate/error`. Never put `eventId`, `orderId`, `customerId`, or raw payloads into Prometheus labels; use controlled audit/log/trace IDs to reconcile single events.

## 15. Testing Every Boundary

### 15.1. Unit Testing Producer Callbacks

Test these cases:

1. `send(...)` returns an incomplete future: do not record BROKER_CONFIRMED.
2. Future completed normally: update only broker confirmed.
3. Future failed: keep outbox retryable/unknown per policy.
4. Rabbit confirm ACK with unroutable return: do not treat as queued for consumers.
5. Callback skipped on process crash: outbox can still replay.

This tests the **publish adapter**, not consumer end-to-end processing.

### 15.2. Testing SQL Inbox Idempotency

An integration test with PostgreSQL Testcontainers should assert:

~~~text
Given eventId=E-100 and orderId=ORD-100
When consumer applies event first time
Then inbox has one row for (consumer, E-100)
And reporting business state is updated once

When the same E-100 is delivered again
Then inbox still has one row
And business effect is not applied twice
~~~

For concurrent duplicate deliveries, test two transactions trying to insert `(consumer_name,event_id)` simultaneously; the unique constraint must guard the race. Do not rely on `SELECT exists` in application code without a unique constraint.

### 15.3. Testing Crash Between DB COMMIT and ACK

~~~text
Given consumer received E-100
And SQL transaction committed business + inbox
When process crashes before consumer ACK
And broker redelivers E-100
Then consumer detects duplicate
And no extra business effect occurs
And consumer can ACK again safely
~~~

This is the most critical test for at-least-once consumers. While mock listeners can demonstrate logic, real tests require real DB transactions and broker behavior.

### 15.4. Kafka Integration Tests

Use EmbeddedKafka or Kafka Testcontainers to verify:

- Kafka producer futures, partition keys, and record metadata.
- Manual ack mode and committed group offsets.
- Consumer failure before DB commit triggers retry.
- Consumer crash after DB commit, replay, and inbox deduplication.
- Rebalances/concurrency do not violate aggregate ordering policy.
- DLT/parking semantics and business status.

A single-node Kafka test broker does not prove multi-broker durability/ISR failover. If HA guarantees matter, also test an environment matching production topology.

### 15.5. RabbitMQ Integration Tests

Use RabbitMQ Testcontainers or a test broker instance:

- Exchanges, routing keys, queue bindings, publisher confirms.
- Unroutable mandatory return despite confirm ACK.
- Manual consumer ACK after business commit.
- Nack/requeue and DLX behavior.
- Listener crash before ACK causes redelivery.
- Queue durability/persistence/quorum under real config.

Never run load tests against a production broker without authorization and strict safety limits.

### 15.6. Testing Asynchronous Handoff

If a consumer merely hands work to an executor and ACKs:

~~~text
Consumer receives E-100
    |
    +-- executor.submit(task)
    |
    +-- consumer ACK
    |
    +-- JVM crashes before task runs
~~~

That **loses work** if the task was not durably persisted. Tests should inject a crash or stop the consumer right after handoff and verify a durable work table/queue still retains ownership; ACK only after durable handoff.

## 16. Runbook When Producer Reports Success Yet Consumer Sees Nothing

1. Verify the producer actually awaited the future/confirm rather than merely seeing no exception on send.
2. Check Kafka `acks` and topic replication/min ISR; check RabbitMQ confirms/returns/routing.
3. Verify topic/partition or exchange/routing key/queue match the environment.
4. Check retention/TTL, DLT/DLQ, queue policies, and whether a consumer already ACKed it.
5. Verify consumer group/queue bindings, broker ACL permissions, and credentials.
6. Check Kafka committed offsets/lag or RabbitMQ ready/unacked counts, prefetch, and requeues.
7. Inspect handler logs, schema errors, SQL transaction states, inbox, and business tables.
8. Check whether redeliveries/duplicates are being handled cleanly or mistakenly filtered out.
9. Reconcile stable eventId/operationId across producer and consumer audit logs.
10. Replay under control without generating a new eventId for the same publish intent.

### 16.1. Quick Diagnostic Table

| Symptom | Likely Cause | Check |
| --- | --- | --- |
| Kafka send does not throw | Send was merely queued async | Future/callback and `acks` |
| Kafka offset exists | Broker wrote the record | Consumer group / business outcome |
| Kafka lag is 0 yet report is missing | Early ACK/offset commit or handler skipped it | Inbox, DB transactions, errors |
| Rabbit confirm ACK yet queue is empty | Unroutable or consumer already ACKed | Publisher returns and bindings |
| Rabbit unacked grows | Slow worker, DB pool exhausted, hung handler | Prefetch, database locks, thread metrics |
| Continuous redelivery loop | Poison message, zero-delay requeue | DLQ / error taxonomy |
| Duplicate after crash | DB COMMIT before ACK | Inbox / idempotency |
| Outbox BROKER_CONFIRMED yet report missing | Consumer lag, DLT, or failure | Consumer business completion |
| DLT count rises yet success dashboard stays green | Conflated producer confirmed with applied | Separate success counters |

**Never alter offsets, purge queues, or force-ack** to “clear backlog” before verifying business state and recovery paths.

## 17. Security and Data Contracts

- Kafka/RabbitMQ/JMS clients must use appropriate TLS/mTLS/SASL/auth; verify certificates and hostnames.
- Broker ACLs must restrict publish/consume per topic, exchange, queue, and service identity.
- Never hardcode secrets in YAML/repositories; never write raw payloads containing PII into logs or metric tags.
- Validate serializer/`schemaVersion` and business constraints on both producer and consumer sides.
- Never trust unauthenticated external callers' self-declared `tenantId`/`eventType`/`operationId`.
- Enforce retention, dead-letter, and audit lifecycles matching data sensitivity.
- Isolate staging/test topics, consumer groups, and credentials from production.

A broker ACK reflects protocol/broker contracts—it **does not prove a message is business-valid or that the service is authorized to act for a tenant**. Authorization must still be checked at application/domain boundaries.

## 18. Implementation Checklist

- [ ] Distinctly named send invoked, broker confirmed, delivered, business applied, and consumer acknowledged.
- [ ] Producer does not treat async send return as a broker ACK.
- [ ] Kafka `acks`/idempotence/min ISR/topic replication configured and tested per policy.
- [ ] RabbitMQ publisher confirms, mandatory returns, and queue bindings verified separately.
- [ ] Consumer ACK/offset commit occurs only after business commit or appropriate **durable handoff**.
- [ ] No in-memory RAM queue/callback used as proof of durability.
- [ ] Producer uses transactional outbox when coordinating with SQL.
- [ ] Consumer updates inbox/unique constraint and business state in the same local transaction.
- [ ] Event ID/operationId remains stable across retries; trace ID/offset never substitutes for business identity.
- [ ] DLQ/parking treated as pending error state, never business success.
- [ ] Backoff/retry budgets, permanent vs. transient classification, and retry-storm safeguards in place.
- [ ] Ordering/version guards applied when multiple events for one aggregate mutate shared state.
- [ ] Tests cover crashes before/after producer confirm, DB COMMIT, and consumer ACK.
- [ ] Separate metrics exist for producer acknowledgements, consumer deliveries, applied/duplicate, lag, and DLT.
- [ ] Broker TLS/ACL/secrets, schema evolution, and payload privacy enforced.

**Key takeaway:** **Sent**, **broker received**, and **consumer processed** are three distinct milestones. Producer futures/publisher confirms reflect publish outcomes per broker configuration; Kafka offset commits or RabbitMQ consumer ACKs reflect consumption progress; only a **reliable business commit or completion event** proves the business effect completed. Production integrations must combine outbox, inbox/idempotency, bounded retries, failure-window tests, and layered observability.

## References

- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs): acks, retries, idempotence, and producer delivery timeouts.
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs): group offsets, auto commit, and isolation.
- [Apache Kafka — Delivery Semantics](https://kafka.apache.org/documentation/#semantics): at-most-once, at-least-once, and scoped exactly-once.
- [Spring Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): KafkaTemplate futures and callbacks.
- [Spring Kafka — Message Listener Container](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): manual acknowledgement and offset commits.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): both ACK types and failure handling.
- [RabbitMQ — Reliability](https://www.rabbitmq.com/docs/reliability): durability, broker failures, and recovery.
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): RabbitTemplate/CorrelationData and returned messages.
- [Spring AMQP — Receiving Messages](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): listener containers and acknowledgment modes.
- [Spring Framework — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): JMS listeners, sessions, and transaction semantics.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): deduplication and safe replay.

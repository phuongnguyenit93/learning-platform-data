# Transaction Boundaries and Delivery Guarantees When Bridging Brokers

Spring Cloud Stream lets an application connect to multiple messaging systems using multiple binders. For example, a function can read orders from Kafka and send events to RabbitMQ; another bridge can transfer data from RabbitMQ to Pulsar. Binders unify how bindings are declared and messages are processed, yet each broker retains its own transaction coordinator, acknowledgement mechanism, and storage boundary.

When bridging brokers, a business operation typically consists of at least two independent steps: acknowledging the message on the source broker and publishing the message to the target broker. If the application commits/acks the source before the target receives the message, a failure can cause data loss. If it publishes to the target first and the application stops before committing/acking the source, the message will be redelivered and may create duplicates. This is the dual-write problem between two distributed systems.

No property that enables multiple binders automatically turns two brokers into a single distributed transaction. A Kafka transaction can combine source offsets and Kafka output within the same Kafka transaction; a Pulsar transaction can combine acknowledgements and writes within Pulsar's transaction scope; RabbitMQ uses consumer acknowledgements and publisher confirms independently for the two directions. When bridging across different broker types or independent clusters, delivery guarantees must be designed at the application level, typically using at-least-once delivery, stable event IDs, idempotency, and transactional outbox/inbox.

This lesson explains transaction boundaries, message loss/duplication windows, how to choose delivery guarantees, multi-binder configuration, direct bridge vs. outbox-backed bridge design, ordering, retries/DLQ, observability, and failure testing.

## Learning objectives

After this lesson, you can:

- Configure each binding to use a separate binder and broker in Spring Cloud Stream.
- Distinguish the local transaction scopes of Kafka, RabbitMQ, and Pulsar.
- Explain why multiple binders do not create a distributed transaction across brokers.
- Identify the two failure windows that cause message loss or duplication when bridging.
- Choose between at-most-once, at-least-once, or effectively-once based on requirements.
- Design a direct bridge with publish-to-target-then-ack-source ordering.
- Use transactional outbox/inbox to solve dual-write with a database.
- Design event IDs, deduplication, ordering, and schema mapping.
- Coordinate retries, dead-lettering, quarantine, and replay.
- Test crashes, timeouts, broker outages, and duplicate deliveries.

## 1. Multiple binders do not mean a single transaction

A binder is an adapter connecting a Spring Cloud Stream binding to a messaging system. An application can assign a separate binder to each input/output binding. The function still processes payloads according to the common programming model, while the binder decides how to connect, serialize, publish, consume, and acknowledge messages.

Example of a bridge reading from Kafka and writing to RabbitMQ:

~~~yaml
spring:
  cloud:
    function:
      definition: bridgeOrder
    stream:
      bindings:
        bridgeOrder-in-0:
          binder: kafka
          destination: orders.created
          group: order-bridge
        bridgeOrder-out-0:
          binder: rabbit
          destination: orders.forwarded
~~~

When multiple binders are on the classpath, Spring Cloud Stream requires explicitly specifying a binder for each binding or configuring a default binder. If the application connects to multiple brokers of the same type, you can declare named binder configurations with separate connection environments.

Example connecting two brokers of different types using binder configurations:

~~~yaml
spring:
  cloud:
    function:
      definition: bridgeOrder
    stream:
      bindings:
        bridgeOrder-in-0:
          binder: kafkaSource
          destination: orders.created
          group: order-bridge
        bridgeOrder-out-0:
          binder: rabbitTarget
          destination: orders.forwarded
      binders:
        kafkaSource:
          type: kafka
          environment:
            spring:
              kafka:
                bootstrap-servers: kafka.internal:9092
        rabbitTarget:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                host: rabbit.internal
                port: 5672
                username: ${RABBIT_USER}
                password: ${RABBIT_PASSWORD}
~~~

The names `kafkaSource` and `rabbitTarget` are binder configuration names chosen by the application. With explicit binder configuration, declare all required binders completely because automatic default binder discovery is replaced. Do not put secrets directly into configuration files; use environment variables or a secret manager.

### 1.1. The function only creates the processing flow

Example bridge function:

~~~java
@Bean
Function<OrderCreated, OrderForwarded> bridgeOrder() {
    return order -> new OrderForwarded(
            order.eventId(),
            order.orderId(),
            order.customerId(),
            order.totalAmount(),
            order.createdAt(),
            1);
}
~~~

This function transfers the payload from the input binding to the output binding. Spring Cloud Stream does not automatically create a transaction spanning both brokers because of this. When the input is committed/acked and at what level the output is confirmed still depend on the binder, configuration, and producer client.

### 1.2. Transaction boundaries

~~~text
             Spring Cloud Stream application
       +------------------------------------------+
       | Function / message handler               |
       |                                          |
       | Input binding             Output binding |
       +------|--------------------------|---------+
              v                          v
        Source broker              Target broker
        Transaction A              Transaction B
~~~

Each binder manages connections and resources for its own broker. A transaction manager tied to Kafka cannot automatically enlist a RabbitMQ publish or Pulsar acknowledgement into a Kafka transaction. Likewise, a Pulsar transaction does not automatically encompass a Kafka offset or RabbitMQ delivery tag.

Even if transaction managers are synchronized via callbacks or committed sequentially, that does not create a shared atomic commit protocol across brokers. If the first resource commits successfully and the second resource fails, the system still ends up in a partially committed state.

## 2. Two failure windows of a bridge

Suppose a bridge receives message E from Kafka and forwards it to RabbitMQ. There are two critical operations:

- P: publish E to RabbitMQ and receive target confirmation.
- A: commit the Kafka offset to confirm E has been processed.

Without a shared transaction between the two brokers, the ordering of P and A creates a trade-off.

### 2.1. Commit source first, publish target second

~~~text
1. Kafka delivers E
2. Bridge commits Kafka offset
3. Bridge publishes E to RabbitMQ
4. Process stops before RabbitMQ receives E
~~~

Kafka will not redeliver E because the offset was already committed. RabbitMQ does not have E either. The message is lost from the bridge flow.

This behaves like at-most-once: a message is never processed twice by the bridge, but may fail to reach the target.

### 2.2. Publish target first, commit source second

~~~text
1. Kafka delivers E
2. Bridge publishes E to RabbitMQ
3. RabbitMQ confirms the publish
4. Process stops before Kafka commits the offset
5. Kafka redelivers E after the bridge restarts
6. Bridge publishes E again
~~~

RabbitMQ may receive two copies of E. This is the duplicate window. However, the message is not lost: Kafka still holds responsibility for redelivering it because the offset has not been committed.

This is the foundation of at-least-once: prioritizing zero message loss and accepting the possibility of duplicates. To achieve near-exactly-once business behavior, the target consumer must detect and ignore duplicates using a stable event ID.

### 2.3. Ordering decision table

| Ordering | Failure between steps | Consequence |
|---|---|---|
| Commit/ack source then publish target | Process stops after source commit | Possible message loss |
| Publish target then commit/ack source | Process stops after target publish | Possible duplicate publish upon source redelivery |
| Persist inbox/outbox durably then ack source | Process stops after DB commit, before source ack | Source redelivers; inbox deduplicates |
| Publish outbox then mark sent | Process stops after publish, before marking sent | Relay republishes; target deduplicates |

When two systems lack a shared transaction, no ordering of two commands eliminates all failure windows. The design must make retries safe.

## 3. Three levels of delivery guarantees

Delivery guarantee terms must be understood within the scope of a specific hop and a specific side effect.

| Guarantee | Meaning | Main risk |
|---|---|---|
| At-most-once | Message is delivered at most one time | Can be lost if source is acknowledged too early |
| At-least-once | Message is redelivered until appropriate confirmation is received | Duplicates can occur |
| Exactly-once within a transaction | Operations in the same transaction commit or roll back together | Applies only within supported resources/transactions |
| Effectively-once | Can be delivered multiple times, but business side effect is applied only once via idempotency/deduplication | Requires durable storage of event IDs and processing state |

### 3.1. Exactly-once is not a system-wide property

Kafka EOS can combine reading, processing, and writing Kafka output within a single Kafka transaction; the input offset is sent to the transaction. This is useful for consume-process-produce within the same Kafka transaction scope. It does not automatically include a database commit, HTTP call, or publish to RabbitMQ.

A transaction protects the atomicity of output writes and committed offsets; it does not mean the handler code runs strictly once. After a rollback, records may be redelivered and processing logic may run again. Any side effect outside the Kafka transaction still requires idempotency or its own mechanism.

Pulsar transactions support atomic writes and acknowledgements across multiple topics/partitions within a Pulsar transaction scope. Spring for Apache Pulsar can combine listener acknowledgement with a transactional PulsarTemplate. That does not extend a Pulsar transaction to cover Kafka or RabbitMQ.

RabbitMQ has publisher confirms and consumer acknowledgements, yet these two mechanisms are independent of each other. Publisher confirm only confirms the target broker has accepted responsibility for the publish; consumer ack confirms the bridge handled delivery from the source. A confirm does not commit a Kafka offset, and a Rabbit ack does not confirm RabbitMQ received a publish from another binder.

Therefore, when describing a bridge as effectively-once, state it accurately: messages may be delivered multiple times, but the target consumer uses event IDs and a database transaction so the business side effect is applied only once.

## 4. Transaction scope of each broker

### 4.1. Kafka transaction

The Kafka binder supports transactions when a non-empty transaction ID prefix is configured:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: bridge-kafka-${INSTANCE_ID}-
~~~

In a processor application, the consumer starts a transaction. Records sent on the consumer thread participate in that transaction; when the listener completes normally, the container sends the offset to the transaction and commits. Transactional producer bindings share the producer factory configured under `transaction.producer`.

Kafka transactions are suitable when:

- Input is read from Kafka.
- Output is written to topics within the same Kafka transaction scope.
- Source offsets and Kafka output need to commit/roll back together.

If the output binding uses the Rabbit binder, the Rabbit publish does not participate in the Kafka transaction. If two Kafka binders connect to two different clusters, there is no automatic transaction spanning both clusters. Inspect the specific binder names, producer factories, and transaction managers.

When a Kafka transaction rolls back, retries and dead-lettering are handled separately by the container. Normal binder retry/DLQ does not behave the same as non-transactional flows because retry records published inside the original transaction may be rolled back with the transaction. Configure `AfterRollbackProcessor` and test thoroughly.

### 4.2. RabbitMQ acknowledgement and publisher confirm

RabbitMQ has two independent acknowledgements:

- Consumer acknowledgement: the bridge informs the source queue that the delivery has been processed.
- Publisher confirm: the target broker informs the publisher that the publish has been accepted by the broker under queue semantics.

A RabbitMQ-to-Kafka bridge can publish to Kafka and then ack the RabbitMQ delivery after knowing the publish result. If the process stops after the Kafka commit but before the Rabbit ack, RabbitMQ may redeliver the message and Kafka receives a duplicate.

With RabbitMQ as the target, publisher confirms verify the broker accepted the publish. If a message fails to route to any queue, the publisher can use `mandatory` and handle `basic.return`; confirm does not mean a consumer has already processed the message.

Do not enable auto-ack for a critical bridge consumer if messages would be acknowledged the moment the broker writes them to the socket. Use manual acknowledgement or equivalent binder behavior, and acknowledge the message only after the target has taken responsibility for the data.

### 4.3. Pulsar transaction

Pulsar native transactions can combine:

- Publishing messages to multiple topics/partitions.
- Acknowledging consumed messages.
- Committing all operations or aborting all operations in the transaction.

With Spring for Apache Pulsar, a transactional listener container starts a transaction; acknowledgements are enlisted in the transaction; sends via a transactional PulsarTemplate join the active transaction. This supports consume-process-produce inside Pulsar.

A Pulsar transaction only covers operations enlisted in that Pulsar transaction. Sending to Kafka or RabbitMQ does not automatically join that transaction. If using the Spring Cloud Stream Pulsar binder, verify whether your binder version exposes the desired transaction behavior; do not assume every PulsarTemplate configuration automatically applies to binder bindings.

### 4.4. Scope matrix

| Source | Target | Mechanisms that can coordinate | Limitation |
|---|---|---|---|
| Kafka | Kafka in same transaction scope | Kafka transaction: output and input offset | Excludes DB/HTTP or other clusters |
| Pulsar | Pulsar in same transaction | Pulsar transaction: output and input acknowledgement | Excludes Kafka/Rabbit |
| RabbitMQ | RabbitMQ | Consumer ack and publisher confirm; channel transaction within Rabbit | Confirm and ack remain two separate mechanisms |
| Kafka | RabbitMQ | Kafka offset commit and Rabbit publisher confirm in application order | No atomic cross-broker commit |
| RabbitMQ | Pulsar | Rabbit consumer ack and Pulsar publish/transaction | No atomic cross-broker commit |
| Pulsar | Kafka | Pulsar acknowledgement and Kafka producer transaction | No atomic cross-broker commit |

## 5. Direct bridge with at-least-once

A direct bridge is a simple choice when duplicates are acceptable and the target consumer can be made idempotent.

Workflow:

1. Receive message from source broker.
2. Validate schema and event ID.
3. Convert payload to canonical event envelope.
4. Publish to target broker.
5. Wait for publish confirmation per the target binder/client mechanism.
6. Only after the publish is confirmed, let the binder commit the offset or ack the source message.
7. If publishing fails or the outcome is unknown, do not acknowledge the source; allow retry.

~~~mermaid
sequenceDiagram
    participant S as Source broker
    participant B as Bridge
    participant D as Target broker
    S->>B: Deliver event E
    B->>B: Validate and map envelope
    B->>D: Publish E
    D-->>B: Confirm/ack publish
    B-->>S: Commit offset / consumer ack
    Note over B,D: Crash after confirm, before source ack may create duplicate
~~~

### 5.1. Broker-level confirmation is required

A message send call returning successfully at the application layer does not always mean the target broker has durably written the message. Depending on the binder, `send` may only confirm that the channel accepted the message for asynchronous processing.

For a reliable bridge:

- Identify which API returns the actual publish outcome.
- Use publisher confirms/acks or transaction commits of the target broker.
- Check for unroutable messages and broker nacks.
- Acknowledge the source only after the target has accepted responsibility.
- Set timeouts and treat indeterminate outcomes as potential duplicates.

Spring Cloud Stream standardizes bindings, but does not provide a single generic confirm type with identical semantics across Kafka, RabbitMQ, and Pulsar. When waiting for broker-specific confirmation is required, use the corresponding binder/client capability or choose an outbox architecture.

### 5.2. Function example solely to illustrate mapping

~~~java
@Bean
Function<OrderCreated, OrderForwarded> bridgeOrder() {
    return order -> new OrderForwarded(
            order.eventId(),
            order.orderId(),
            order.customerId(),
            order.totalAmount(),
            order.occurredAt(),
            1);
}

record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        Instant occurredAt) {}

record OrderForwarded(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        Instant occurredAt,
        int schemaVersion) {}
~~~

This example shows how to move a payload from the input binding to the output binding. It does not by itself prove the target broker confirmed before the source committed. With asynchronous binders, verify publish results or use an outbox relay to decouple durable message storage from source acknowledgement.

## 6. Transactional outbox/inbox for a reliable bridge

When zero event loss across broker boundaries must be guaranteed, a strong option is using a database as an intermediate durable store. Inbox records events received from the source; outbox stores events to be sent to the target. Writing to inbox and outbox happens in the same database transaction.

~~~mermaid
flowchart LR
    A[Source broker] --> B[Bridge consumer]
    B --> C[(DB transaction)]
    C --> D[Inbox: source event ID]
    C --> E[Outbox: target event]
    E --> F[Outbox relay]
    F --> G[Target broker]
    G --> H[Target consumer]
    H --> I[(Target inbox / business DB)]
~~~

### 6.1. Ingesting from the source broker

1. Consumer receives event E with a stable `eventId`.
2. Open a database transaction.
3. Insert `eventId` into `bridge_inbox` with a unique constraint.
4. If `eventId` already exists, do not create another outbox row.
5. If it is a new event, write the payload/canonical envelope into `bridge_outbox`.
6. Commit the database transaction.
7. Only after the database transaction commits successfully, return success from the handler so the binder commits the offset or acks the source.

If the process stops after step 6 but before step 7, the source broker redelivers the event. The unique constraint in `bridge_inbox` detects the duplicate; the application does not create another outbox row. The event is already durably stored and is not lost.

### 6.2. Illustrative table schema

~~~sql
CREATE TABLE bridge_inbox (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE bridge_outbox (
    outbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id VARCHAR(200) NOT NULL,
    destination VARCHAR(200) NOT NULL,
    payload JSON NOT NULL,
    aggregate_id VARCHAR(200),
    aggregate_sequence BIGINT,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    UNIQUE (destination, event_id)
);
~~~

The DDL above is illustrative; JSON type, identity, timestamp, and unique constraint syntax depend on the database. If per-aggregate ordering must be preserved, store `aggregate_id` and `aggregate_sequence` so the relay can publish sequentially by key.

Example service writing inbox and outbox in the same database transaction:

~~~java
@Service
class BridgeInboxService {

    private final BridgeInboxRepository inbox;
    private final BridgeOutboxRepository outbox;

    BridgeInboxService(
            BridgeInboxRepository inbox,
            BridgeOutboxRepository outbox) {
        this.inbox = inbox;
        this.outbox = outbox;
    }

    @Transactional
    public void store(OrderCreated event) {
        boolean firstDelivery =
                inbox.insertIfAbsent("order-bridge", event.eventId());

        if (!firstDelivery) {
            return;
        }

        outbox.save(BridgeOutbox.from(event));
    }
}

@Bean
Consumer<OrderCreated> bridgeInput(BridgeInboxService service) {
    return service::store;
}
~~~

`insertIfAbsent` must be implemented using a unique constraint and an atomic database insert; do not use SELECT-then-INSERT because two concurrent consumers can both pass the check. The service must be invoked through a Spring proxy so `@Transactional` actually opens a transaction. The handler only returns success after the service transaction has committed; do not offload inbox/outbox persistence to an asynchronous task and ack the source early.

### 6.3. Outbox relay

The relay reads unpublished rows, sends payloads to the target broker, and waits for publish confirmation. Only after receiving appropriate confirmation does it mark `published_at`.

~~~text
SELECT outbox rows
  WHERE published_at IS NULL
  ORDER BY outbox_id
  FOR UPDATE SKIP LOCKED

For each row:
  publish to destination
  wait for broker-specific confirmation
  if confirmed:
      mark published_at
  else:
      increment attempts and store error
~~~

Avoid holding a database transaction open while waiting on the broker for long periods whenever possible. A common pattern is claiming rows via a status/lease in a short transaction, publishing outside the transaction, and then updating the result in a new transaction. Leases must have a timeout so another worker can take over if a process dies.

### 6.4. Duplicate window of the outbox relay

If the target broker received the message but the relay stops before marking the outbox row as published, the relay will resend the row after restarting. This is an intentional duplicate to prevent message loss.

The target consumer needs an inbox/dedup by `eventId`. When the consumer receives a message:

1. Open a database transaction.
2. Insert `eventId` into a `processed_message` table with a unique constraint.
3. If `eventId` already exists, skip business side effects and finish successfully.
4. If new, apply business changes within the same transaction.
5. Commit the database transaction.
6. Only after commit, ack/commit the target message offset.

As a result, multiple deliveries of the same event still apply business changes only once in the target database.

### 6.5. CDC and outbox relay

Instead of polling the outbox table, Change Data Capture (CDC) can read committed rows and publish them to the broker. CDC reduces polling and can preserve database log order, but requires operating the connector, schema history, offsets, and recovery.

Whether using polling or CDC, duplicate publishes can still happen when the relay does not know if the broker received the message before the connection dropped. The target consumer still needs idempotency.

## 7. Event envelope and cross-broker data contract

Do not copy internal message headers from the source broker verbatim to the target broker. Kafka offsets, Rabbit delivery tags, Pulsar MessageIds, consumer group metadata, and broker retry headers are meaningful only within a specific broker.

Define a canonical event envelope:

~~~json
{
  "eventId": "01JORDER8W4M8F6GQY2",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "source": "order-service",
  "occurredAt": "2026-11-24T08:30:00Z",
  "aggregateType": "Order",
  "aggregateId": "order-812",
  "aggregateSequence": 12,
  "correlationId": "checkout-91",
  "traceparent": "00-...",
  "payload": {
    "orderId": "order-812",
    "customerId": "customer-31",
    "totalAmount": 125000
  }
}
~~~

Important fields:

| Field | Purpose |
|---|---|
| eventId | Stable ID for cross-broker deduplication |
| eventType | Business event type |
| schemaVersion | Schema version of the payload |
| source | Service originating the event |
| occurredAt | Business occurrence timestamp |
| aggregateId | Key for preserving per-entity ordering |
| aggregateSequence | Detects duplicates, gaps, and out-of-order events |
| correlationId | Links steps of a workflow |
| traceparent | Propagates trace context per tracing standards |
| payload | Normalized business data |

### 7.1. Schema mapping

Kafka, RabbitMQ, and Pulsar may use different serialization, schema registries, or content types. The bridge needs to:

- Read the source schema.
- Validate the payload.
- Convert to the canonical model or target schema.
- Preserve `eventId` and correlation metadata.
- Write a new `schemaVersion` if transformation changes structure.
- Quarantine invalid payloads instead of retrying infinitely.

Do not use a broker offset as `eventId`. An offset is unique only within a partition/topic and can change during replay or migration. `eventId` must be generated at the source and remain stable across all forwards.

### 7.2. Message size and limits

Brokers impose limits on message size, batch size, and headers. A payload valid on the source broker may exceed the target broker's limit. The bridge should check size after serialization and apply a policy for large payloads: compression, object storage reference, or quarantine.

## 8. Ordering across brokers

At-least-once can create duplicates; multiple relay workers can reorder events. If business logic requires ordering, define the exact ordering scope to protect.

### 8.1. Per-aggregate ordering

Use `aggregateId` as the key/partition key/routing key matching the target broker's capabilities. Store `aggregateSequence` so consumers can detect:

- Duplicate: sequence has already been processed.
- Out-of-order: sequence is smaller or larger than expected.
- Gap: a sequence number in between is missing.

### 8.2. Multiple outbox workers

If multiple workers claim rows independently, event sequence 12 could be published before sequence 11. To preserve order:

- Partition the outbox by `aggregateId`.
- Allow only one worker to process a given aggregate at a time.
- Publish the next sequence only after the previous sequence is confirmed.
- Use a target partition key or routing key based on `aggregateId`.
- The target consumer checks sequence numbers and applies a wait/quarantine policy when detecting a gap.

There is no need to maintain global ordering if business rules only require ordering per `orderId` or `accountId`. Narrowing the ordering scope increases throughput.

## 9. Retries, dead-lettering, and quarantine in a bridge

Bridge errors should be categorized:

| Error category | Example | Action |
|---|---|---|
| Transient | Target broker disconnected, timeout, throttling | Retry with exponential backoff and jitter |
| Recoverable via operations | Expired credentials, missing ACL | Pause retry escalation, alert, and resume after fixing |
| Permanently invalid data | Invalid schema, payload exceeds limit | Quarantine/DLQ |
| Duplicate | `eventId` already processed | Ack/commit successfully after dedup |
| Ordering conflict | Sequence has a gap or is out-of-order | Bounded retry or isolate by aggregate |

### 9.1. Retrying without losing events

If using a direct bridge, do not ack/commit the source before knowing the target received the message. If using an outbox, do not delete the outbox row before publish is confirmed. Record attempt count, last error, next retry time, and destination.

### 9.2. DLQ and quarantine

A DLQ holds unprocessable messages for investigation. Quarantine should keep the canonical envelope, `eventId`, source broker, destination, error, and attempt count. Do not automatically replay schema-failed or business-failed messages without fixing the root cause.

When replaying:

1. Preserve the original `eventId`.
2. Record who or which workflow triggered the replay.
3. Choose the right destination and schema version.
4. Use an idempotent consumer.
5. Monitor duplicates and business outcomes.

### 9.3. Avoiding retry storms

If the target broker goes down, fast retries across every message can exhaust threads, connections, and the database. Use exponential backoff, jitter, bounded concurrency, circuit breakers, or appropriate pause/resume. An outbox holds backlog durably while the relay throttles down.

## 10. Transactions with databases and brokers

A bridge may update a database and send a message. If DB commit and broker publish are two separate operations, this is also a dual-write.

Risk example:

~~~text
DB commit succeeds
    |
    +-- process crashes before publish
            -> DB changed, event not sent

Publish succeeds
    |
    +-- DB rolls back
            -> downstream sees an event inconsistent with DB
~~~

Transactional outbox writes business data and the event row in the same database transaction. The relay reads committed event rows and publishes afterward. This is a standard way to avoid DB/message dual-write.

### 10.1. Spring transaction synchronization is not a distributed atomic commit

Spring can synchronize callbacks between transaction managers or invoke multiple transaction managers sequentially. This can help order commits and rollbacks in some scenarios, but does not provide a shared two-phase coordinator across Kafka, RabbitMQ, Pulsar, and a database.

If the first resource commits and the second resource fails, you cannot assume the first resource automatically rolls back. Use outbox/inbox or sagas when consistency across multiple services is needed.

### 10.2. Sagas for multi-service workflows

If the bridge only forwards events, outbox/inbox is usually sufficient. If the workflow also executes multiple independent business changes such as reserving inventory, charging payment, and creating a shipment, use a saga:

- Each service commits its local transaction.
- Services emit outcome or failure events.
- An orchestrator/choreography decides the next step.
- If a later step fails, execute compensating actions.

A saga does not create a system-wide ACID transaction; it manages eventual consistency across steps and compensating actions.

## 11. Configuring and operating multiple binders

### 11.1. Selecting a binder per binding

Declare the binder by binding name:

~~~properties
spring.cloud.stream.bindings.bridgeOrder-in-0.binder=kafkaSource
spring.cloud.stream.bindings.bridgeOrder-out-0.binder=rabbitTarget
~~~

If there are multiple brokers of the same type, declare each binder configuration with its own `type` and `environment`. When using explicit binder configuration, every required binder must be listed.

### 11.2. Kafka transaction settings do not apply to Rabbit output

Example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: bridge-kafka-${INSTANCE_ID}-
~~~

This property enables transactions for the Kafka binder. It does not make a Rabbit output binding part of the Kafka transaction. If the input is Kafka and the output is Rabbit, you must use the at-least-once/outbox bridge mechanism described above.

### 11.3. Separating configuration and access permissions

Each binder has its own endpoints, credentials, TLS, truststore, retries, and timeouts. Make sure to:

- Use separate secrets for each broker.
- Restrict consumer permissions at the source and producer permissions at the target.
- Configure TLS/hostname verification.
- Never log credentials or sensitive payloads.
- Set connection timeouts and retries tailored to each broker's characteristics.
- Monitor each binder's health independently.

A failing target broker does not necessarily mean the source broker is failing. With an outbox, the source can continue ingesting and storing events within database capacity limits; the relay will deliver them when the target recovers.

## 12. Testing delivery guarantees

Testing only that a function returns the expected object is insufficient. You must test broker acknowledgements, offsets/acks, duplicates, and failure windows.

### 12.1. Testing mapping and schemas

- Send sample events from the source broker.
- Verify the event envelope on the target broker.
- Check `eventId`, `aggregateId`, `schemaVersion`, and `payload`.
- Verify broker-specific headers are not used as business identity.
- Test oversized payloads and invalid schemas.

### 12.2. Testing crashes at each point in time

Create controlled failure points:

1. After source delivers the message but before the bridge processes it.
2. After publishing to target but before receiving confirm.
3. After receiving target confirm but before committing/acking source.
4. After DB inbox/outbox commit but before source ack.
5. After target publish succeeds but before marking the outbox row as sent.
6. After target consumer commits DB but before acking target message.

Verify:

- No messages are lost beyond the chosen guarantee.
- Duplicates can appear in indeterminate-outcome windows.
- Deduplication prevents repeated business side effects.
- Outbox rows are not deleted before publish is confirmed.
- Messages are replayed after broker recovery.

### 12.3. Testing broker outages

- Shut down or disrupt the target broker.
- Verify the source is not acked prematurely.
- With an outbox, verify events are stored and backlog grows in a controlled manner.
- Restore the target broker and verify the relay resumes.
- Verify retries do not trigger a storm or exhaust pools.

### 12.4. Testing ordering and duplicates

Send multiple events with the same `aggregateId` and increasing sequence numbers. Run the relay with multiple workers and inject retries. Verify the target consumer applies sequences in order or detects gaps per policy. Resend the same `eventId` multiple times and verify side effects execute only once.

### 12.5. Test binder and integration tests

The Spring Cloud Stream Test Binder is useful for testing functions and binding logic in a simple environment. It does not fully simulate broker transactions, publisher confirms, consumer acks, partition assignments, or broker failures.

Add integration tests with real brokers or Testcontainers for each binder type used. If a bridge connects Kafka and RabbitMQ, test both brokers in the same test and verify the final state on each side.

## 13. Observability and operations

Track every hop of the bridge:

| Metric | Meaning |
|---|---|
| Source consumer lag | Backlog at the source broker |
| Source ack/commit latency | Time to acknowledge source |
| Target publish confirm latency | Time for target broker confirmation |
| Target nack/return/error rate | Failed or unroutable publishes |
| Outbox pending count | Number of events waiting to be sent |
| Oldest outbox age | Age of the longest-waiting event |
| Outbox retry count | Number of relay retry attempts |
| Inbox duplicate count | Number of duplicate events received |
| Quarantine/DLQ depth | Messages requiring investigation |
| End-to-end event age | Event age from `occurredAt` to target processing |
| Per-broker connection health | Connection health per broker |

### 13.1. Alerting

Consider alerting when:

- Source lag grows while target publishing fails.
- Target confirm latency exceeds SLA.
- Outbox pending count or oldest age grows continuously.
- Quarantine/DLQ receives unexpected new messages.
- Duplicate rate spikes sharply.
- Aggregate sequence gaps appear.
- A binder remains disconnected for an extended period.
- The outbox database approaches storage limits.

Dashboards should distinguish events received from source, events durably stored in outbox, events confirmed by target broker, and events processed by target consumer. These four states are not synonymous.

## 14. Common mistakes

1. **Assuming multiple binders create one shared transaction**: binders only select middleware for bindings. Identify the transaction manager and broker scope of each operation.
2. **Acking source before target receives the message**: a process crash can lose events. Publish/confirm target first or persist to a durable outbox.
3. **Publishing target then acking source without deduplication**: a crash between steps creates duplicates. Keep `eventId` and use an inbox/unique constraint.
4. **Treating `send()` success as durable broker persistence**: channel acceptance differs from publisher confirmation. Verify binder/client semantics.
5. **Using Kafka transactions for Rabbit/Pulsar output**: outputs on other brokers do not join Kafka transactions. Use an outbox or an at-least-once bridge.
6. **Using Pulsar transactions to commit Kafka offsets**: Pulsar transactions do not cover Kafka. Keep expectations within Pulsar's transaction scope.
7. **Confusing Rabbit publisher confirm with consumer ack**: two independent mechanisms that do not confirm each other. Check both sides.
8. **Using `@Transactional` without specifying the resource**: a single chosen transaction manager does not automatically manage all binders. Specify the concrete transaction manager.
9. **Using `ChainedTransactionManager` as 2PC**: sequential commits can still leave partial state. Use outbox/inbox for reliability.
10. **Marking outbox sent before publisher confirm**: crashes can lose events. Only mark sent after target confirmation.
11. **Failing to preserve order with multiple relay workers**: later events may arrive before earlier ones. Partition by aggregate and use sequence numbers.
12. **Using offsets or delivery tags as `eventId`**: these identifiers are meaningful only inside the source broker. Use a stable business ID.
13. **Retrying schema errors infinitely**: poison messages consume resources. Classify errors and quarantine.
14. **Replaying with a new `eventId`**: consumers treat the replay as a new event and repeat side effects. Preserve the original `eventId`.
15. **Testing functions solely with Test Binder**: tests do not prove broker confirm/ack or failure recovery. Integration test both brokers.

## 15. Broker bridge design workflow

When implementing a bridge with Spring Cloud Stream:

1. List the source broker, target broker, and binder name for each binding.
2. Identify the real transaction boundary of each broker.
3. Choose the delivery guarantee per hop and explicitly state duplicate possibilities.
4. Define a canonical event envelope with a stable `eventId`.
5. Decide between a direct bridge and a database inbox/outbox.
6. If using a direct bridge, publish and wait for target confirmation before source ack/commit.
7. If using an outbox, commit inbox/outbox before source ack and only mark sent after target confirmation.
8. Make the target consumer idempotent using `eventId` and unique constraints.
9. Design ordering by `aggregateId` and sequence if required by business logic.
10. Categorize errors, configure retry/backoff, and quarantine.
11. Test crashes at every publish/ack/commit window.
12. Monitor lag, confirms, outbox age, duplicates, and DLQs.
13. Create runbooks for replay, broker outages, schema migration, and backlog handling.

## Conclusion

Spring Cloud Stream allows an application to use multiple binders to read and write across different brokers, but selecting binders does not create a distributed transaction. Kafka transactions only cover Kafka operations participating in the same transaction; Pulsar transactions cover writes/acks enlisted in the Pulsar transaction; RabbitMQ publisher confirms and consumer acknowledgements confirm two directions independently.

With a direct bridge, publishing to the target before acknowledging the source avoids message loss but can create duplicates if the process stops between the two steps. Keep `eventId` stable and make the target consumer idempotent. When high reliability is needed, transactional inbox/outbox durably stores events before source ack, relays publish to the target, and marks sent only after confirmation. Duplicates can still occur after timeouts or crashes, so deduplication, ordering, retries, quarantine, and failure testing are mandatory parts of the design.

## References

- [Spring Cloud Stream — Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-binders.html)
- [Spring Cloud Stream — Connecting to Multiple Systems](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-systems.html)
- [Spring Cloud Stream — Kafka Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/transactional.html)
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [Spring for Apache Pulsar — Transactions](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/transactions.html)
- [Apache Pulsar — Transactions](https://pulsar.apache.org/docs/4.2.x/txn-what/)
- [Transactional Outbox Pattern — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)

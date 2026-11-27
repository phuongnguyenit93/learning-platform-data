# Choosing Messaging for Asynchronous Communication

## Learning Objectives

After this lesson, you can:

- Identify workloads suited for asynchronous messaging between services.
- Distinguish message brokers, event streams, and asynchronous RPC.
- Choose between commands and events based on business meaning.
- Evaluate delivery guarantees, ordering, retries, dead-letter queues, and idempotency.
- Combine messaging with gRPC in a Spring architecture.
- Design publishers/consumers, transactional outbox, and inbox for safe error handling.
- Monitor processing latency, consumer lag, retries, and resilience.

## 1. When Is Asynchronous Communication Appropriate?

In synchronous communication, the caller sends a request and waits for the called service to return a result. Both sides participate in the processing time of the request. If the target service is slow or unavailable, the caller may have to wait, time out, or return an error to the user.

With **asynchronous messaging**, the producer sends a message to a broker or event-streaming platform and continues its own work. The consumer receives and processes the message at an appropriate time. The producer does not need to keep an RPC open until the consumer finishes.

Messaging is appropriate when:

- Work can complete after the initial response, such as sending emails, generating reports, or processing background payments.
- Producers and consumers need to operate independently and be deployed and scaled separately.
- The system needs to absorb traffic bursts using a durable queue or log.
- One event needs to be processed independently by multiple consumers.
- A consumer can temporarily pause and reprocess messages after recovering.
- The business process has multiple steps and does not need a single synchronous response.

Messaging does not automatically make business operations finish faster. It defers processing time to later and helps decouple temporal dependencies between services. Users can receive an ACCEPTED/PENDING status first, then query for the result or receive a notification when processing completes.

## 2. Distinguishing Messaging from Asynchronous gRPC

A gRPC client can use an async stub, callback, or future to avoid blocking the calling thread. However, it is still an RPC: the client calls a specific endpoint, the call has a deadline, and the final result is tied to the called service.

Messaging establishes a different boundary:

- The producer sends a message to a broker without needing a specific consumer to be online.
- The broker retains the message according to its durability/retention policy.
- Independent consumers receive the message and acknowledge processing.
- Producers and consumers can scale, restart, or deploy at different times.
- A message can be delivered to one consumer group or multiple subscriptions depending on the broker.

| Criterion | gRPC RPC | Asynchronous messaging |
| --- | --- | --- |
| Relationship | Caller invokes a specific service | Producer sends to a destination/topic |
| Processing timing | Usually during the call | Consumer processes after receipt |
| Outcome | Response or gRPC status | Ack/receipt on publish; business outcome may arrive later |
| Availability dependency | Caller needs an endpoint able to accept calls | Broker needs to accept messages; consumers can be temporarily offline if messages are stored |
| Buffering | Not a durable queue by default | Broker can store and redeliver |
| Fan-out | Caller must invoke multiple services or use orchestration | One event can have multiple subscriptions/consumer groups |
| Deadline | Has an RPC deadline | Needs message-level expiry/TTL and business deadlines |
| Best fit | Queries/commands needing immediate results | Background workflows, events, buffering, and loose coupling |

Async gRPC keeps the caller from blocking a thread, but it does not replace a broker when durable message storage, replay, fan-out, or independent consumers are required.

## 3. Choosing Commands or Events

The two common message types have different meanings:

- **Command** expresses a request to perform an action: ReserveStock, SendInvoice, or GenerateReport. It is usually directed toward a specific processor responsible for executing the command.
- **Event** expresses a fact that has occurred: OrderCreated, StockReserved, or PaymentSettled. It describes a truth in the domain and may interest multiple consumers.

Event names usually use past tense because the event has already happened. Consumers should not alter the historical meaning of an event; if a new state occurs, the producer emits a new event.

Example when OrderService creates an order:

1. OrderService persists the order successfully.
2. The system emits OrderCreated.
3. BillingService creates a payment request.
4. NotificationService sends a notification.
5. AnalyticsService updates analytics data.

OrderService does not need to call all three services sequentially to complete the order-creation request. However, if the business requires knowing immediately whether payment is accepted, you must design a synchronous response or an explicit status workflow rather than pretending publishing an event means payment has succeeded.

## 4. Message Brokers and Event Streaming

Brokers/queues and event logs can both support asynchronous communication, but they have different operational characteristics:

| Characteristic | Queue/message broker | Event log/stream platform |
| --- | --- | --- |
| Consumption model | Messages are typically delivered to one consumer in a competing group | Consumers read the log by their own offset/position |
| Storage | Usually deletes/removes messages after ack per policy | Usually retains messages by retention, independent of whether consumers have read them |
| Replay | Depends on dead-letter/requeue and broker | Can re-read from an older offset within retention |
| Routing | Can route via exchanges, bindings, and queues | Usually partitioned by key/topic |
| Best suited for | Work distribution, command queues, routing | Event history, high throughput, multiple independent consumers |

RabbitMQ is often used for queues and flexible routing. Kafka is often used for partitioned event logs, consumer groups, and replay. Both have far more capabilities than this condensed comparison table; choose based on durability, ordering, retention, routing, throughput, and the team's operational capability.

Do not choose a broker solely by advertised messages per second. Check publish/consume latency, message sizes, partition/queue counts, replication, retention, failover, and operational cost.

## 5. Producer, Broker, and Consumer Architecture

~~~mermaid
flowchart LR
  A["Order API / OrderService"] -->|"Publish OrderCreated"| B["Message Broker"]
  B --> C["Billing Consumer"]
  B --> D["Notification Consumer"]
  B --> E["Analytics Consumer"]
  C --> F["Billing Database"]
  D --> G["Notification Provider"]
  E --> H["Analytics Store"]
~~~

The producer is responsible for creating messages with a stable schema and identity. The broker is responsible for accepting, storing, and distributing messages according to configuration. The consumer is responsible for validating, processing business logic, and acknowledging message completion according to broker semantics.

Receiving a broker acknowledgement only proves the broker accepted the message at the configured durability level. It does not prove the consumer has completed the business work. If you need to know the processing outcome, design operation status tracking, callback events, or a separate query API.

## 6. Choosing Messaging Alongside gRPC in Spring

In a **SPRING_GRPC** architecture, you can use gRPC for synchronous internal interactions and a broker for asynchronous workflows:

- A REST controller receives requests from the browser.
- The Spring application service calls gRPC to fetch data needed immediately.
- After persisting business changes, the service emits an event through the broker.
- Spring consumers process emails, reports, indexing, or the next workflow step.

Example: OrderService calls InventoryService over gRPC to check or reserve stock in a flow requiring immediate feedback. Once the order is recorded, OrderService emits OrderCreated for BillingService and NotificationService to process independently.

Do not use a broker to replace a query needing an immediate response if the caller has no mechanism to receive the result later. Likewise, do not use sequential gRPC RPCs to broadcast an event to many consumers when broker fan-out has better semantics.

## 7. Designing Message Contracts with Protobuf

If the system already uses Protocol Buffers for gRPC, you can use Protobuf messages as broker payloads. This reuses schemas/code generation, though it does not mean the broker runs the gRPC protocol; the broker simply transports byte payloads.

~~~proto
syntax = "proto3";

package acme.orders.events.v1;

option java_package = "com.acme.orders.events";
option java_multiple_files = true;

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  string customer_id = 3;
  int64 occurred_at_epoch_millis = 4;
  string correlation_id = 5;
}
~~~

The event_id and correlation_id fields serve different purposes:

- event_id uniquely identifies an event, supporting deduplication.
- correlation_id links steps within the same business flow or trace.
- order_id is the aggregate/resource identifier.
- occurred_at represents the business timestamp; do not use the consumer's receipt timestamp in place of when the event occurred.

Set a package/version for schemas and follow Protobuf compatibility rules. Never reuse removed field numbers. Older consumers must ignore unknown new fields and producers should not alter the meaning of existing fields.

## 8. Publishing Messages with Spring Kafka

The following example uses Spring Kafka with serialized Protobuf bytes as the payload. The producer uses the order ID as the record key so events for the same order can be routed to the same partition under the default partitioner:

~~~java
@Component
final class OrderEventPublisher {
    private final KafkaTemplate<String, byte[]> kafkaTemplate;

    OrderEventPublisher(KafkaTemplate<String, byte[]> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    CompletableFuture<SendResult<String, byte[]>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "order-created.v1",
            event.getOrderId(),
            event.toByteArray());
    }
}
~~~

This snippet illustrates the Spring Kafka 3.x API. Serializer, broker, acknowledgement, replication, and timeout settings must be configured per environment. A successful send in the client API does not mean the message is durably stored if broker/producer configuration does not guarantee the required durability.

If publishing is a critical part of a business transaction, do not just call KafkaTemplate after commit and ignore failures. The process can crash between database commit and publishing. The transactional outbox section below solves this failure window.

## 9. Consuming Messages with Spring Kafka

A consumer can use @KafkaListener to process payloads:

~~~java
@Component
final class BillingOrderConsumer {
    private final BillingApplicationService billing;

    BillingOrderConsumer(BillingApplicationService billing) {
        this.billing = billing;
    }

    @KafkaListener(
        topics = "order-created.v1",
        groupId = "billing-service")
    void onOrderCreated(ConsumerRecord<String, byte[]> record)
            throws InvalidProtocolBufferException {
        OrderCreated event = OrderCreated.parseFrom(record.value());
        billing.createInvoice(event);
    }
}
~~~

The listener container manages polling and acknowledgement according to configuration. If the handler throws an exception, the error handler/container decides retry, seek, recovery, or dead-lettering per configured policy. Do not swallow exceptions and treat the message as successfully processed.

Consumers need to validate schema/payload and check the event ID before performing side effects. For unparseable messages, log the error in a controlled way and route them to a dead-letter flow instead of retrying a corrupt payload forever.

## 10. Delivery Guarantees: At-Most-Once and At-Least-Once

Messaging does not inherently guarantee that every message is processed exactly once:

- **At-most-once:** messages may be lost but are never redelivered per policy. Suitable for some droppable telemetry.
- **At-least-once:** messages are redelivered when the broker/client is unsure whether the consumer processed and acknowledged them. Can produce duplicate deliveries.
- **Effectively-once business effect:** the consumer processes at-least-once but uses idempotency/deduplication so the logical side effect happens only once.

A common scenario: the consumer writes an invoice to the database successfully but crashes before committing the offset/ack. Upon restart, the broker redelivers the message. Without consumer idempotency, a duplicate invoice may be created.

Brokers offer transactions or exactly-once processing within specific boundaries, but those boundaries do not automatically encompass external databases, email providers, or HTTP APIs. You must design end-to-end around real transaction boundaries.

## 11. Idempotent Consumers and Inbox

Consumers should use event_id as the deduplication key. An inbox table with a unique constraint on event_id helps detect already-processed events:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Inside a database transaction:

1. Attempt to insert event_id into processed_event.
2. If the unique key already exists, the event was already processed; skip duplicate side effects.
3. If the insert succeeds, apply business changes.
4. Commit the inbox record and business changes in the same transaction.
5. Only ack/commit the offset after the transaction completes according to the chosen acknowledgement mode.

If side effects occur outside the database transaction, such as calling a payment provider, you need an idempotency key or corresponding compensation workflow. An inbox alone cannot make an external HTTP call atomic with the database.

## 12. Transactional Outbox to Prevent Lost Events

Suppose OrderService saves an order to the database and then publishes OrderCreated:

- If the database commits first and the process crashes before publishing, the order exists but the event is lost.
- If publishing happens first and the database rolls back, consumers receive an event for a non-existent order.

Transactional outbox writes business data and the event record in the same database transaction:

~~~text
BEGIN TRANSACTION
  INSERT order (...)
  INSERT outbox_event (event_id, aggregate_id, event_type, payload, ...)
COMMIT

Outbox relay:
  read unpublished events
  publish to broker
  when broker confirms -> mark event as published
~~~

The outbox relay can publish duplicates if the broker received the message but the relay crashed before marking it published. Therefore, consumers must still be idempotent. Outbox solves consistency between the database and the intent to publish; it does not by itself guarantee end-to-end exactly-once processing.

The relay can be implemented via polling or CDC depending on the system. Monitor backlog, retry counts, and the age of unpublished events.

## 13. Ordering and Partition Keys

Message ordering is typically guaranteed only within a specific scope, not system-wide. With Kafka, messages with the same key usually land in the same partition, and order is preserved within a partition. With queue brokers, ordering can be affected by multiple consumers, redelivery, and retries.

If business rules require OrderCreated before OrderPaid for the same order, choose order_id as the key and keep consumer processing aligned. If multiple workers process the same partition in parallel or dispatch messages to an uncontrolled executor, business ordering can break at the application layer.

Do not pick a low-cardinality key or a single key for all messages if it creates a hot partition. Design partition keys to balance required ordering against load distribution.

## 14. Retries, Backoff, and Dead-Letter Queues

Consumers can encounter transient errors like database unavailability or dependency timeouts. Policies should distinguish:

- Transient errors: bounded retries with increasing backoff and jitter.
- Invalid data/contract errors: do not retry endlessly; move to dead-letter or quarantine.
- Business errors requiring intervention: persist failure state and emit operational alerts.
- Max attempts exceeded: route to a dead-letter queue/topic, preserving error metadata and message origin.

Immediate retries can trigger retry storms and overload an already failing dependency further. With queues, immediate retry/requeue can block subsequent messages if the broker preserves order; consider delayed retry queues or dead-letter routing.

A dead-letter queue is not a trash bin. You need a process for observing, fixing errors, replaying safely, and avoiding replaying poison or stale messages.

## 15. TTL, Expiry, and Business Deadlines

Messages can remain in a broker for a long time when consumers fall behind. Not every command remains useful hours later. For example, an OTP send request or a temporary status update may expire.

Set expiry/TTL when semantics permit, and include a business deadline in the message if the consumer must verify validity. Broker TTL can evict messages from a queue per policy, but consumers should still verify the business deadline before applying side effects.

Do not copy a gRPC deadline directly into a message TTL without considering the difference: a gRPC deadline bounds a single call; a message may sit in a broker and be processed minutes later. In async workflows, deadlines belong to operation logic and must be carried in the message.

## 16. Consumer Concurrency and Backpressure

When consumers outpace producers, lag stays low; when producers outpace consumers, backlog grows. A broker absorbs bursts but does not create infinite processing capacity.

Control measures:

- Size partition/queue counts and consumer instances to match throughput.
- Limit concurrency and message poll/prefetch counts.
- Use bounded executors/queues if handlers dispatch background work.
- Monitor consumer lag and oldest message age.
- Pause/resume consumption when downstream is overloaded.
- Limit message size and total in-flight bytes.
- Scale consumers with lag without exceeding dependent database/API limits.

Increasing consumer count does not always increase throughput. If all consumers write to an already saturated database, scaling can accelerate errors and retries.

## 17. Schema Evolution and Compatibility

Producers and consumers can deploy at different times. Therefore, message schemas must remain compatible across versions:

- Prefer adding optional fields with clear default semantics.
- Never reuse removed Protobuf field numbers; use reserved.
- Older consumers must ignore unknown new fields.
- Do not change the meaning of published fields or enum values.
- Version topics/subjects when making incompatible changes.
- Test new producers with old consumers and vice versa in contract tests.

If using Protobuf, payload bytes must be parsed with the matching schema. You can use package versions/topic versions or a schema registry to manage contracts. Never assume sharing a topic means every producer/consumer uses the exact same generated code.

## 18. Observability and Trace Context

A synchronous RPC can be timed from client send to response receipt. With messaging, you need to measure multiple milestones:

- Time the producer created the event.
- Time the broker received/acked it.
- Time the consumer began processing.
- Time the consumer committed/acked.
- Total event age and processing duration.
- Consumer lag, retry count, DLQ count, and outbox backlog.

Include event_id, correlation_id, and trace context in message headers or an envelope by convention. Consumers continue the trace from the producer to observe workflows across services. Do not use event_id or customer_id as high-cardinality metric labels; use traces/logs for detailed identifiers.

Monitor both publish failure rates and consumer failure rates. Successful producer publishes paired with growing consumer lag still indicate that the workflow is not completing on time.

## 19. Securing the Message Broker

Asynchronous communication must secure both transport and access control:

- TLS protects producer/consumer connections to the broker.
- Authentication and authorization restrict who may publish/consume topics or queues.
- Separate credentials per service and apply least privilege.
- Do not include secrets or unnecessary sensitive data in events.
- Encrypt payloads at the application layer when required by the threat model.
- Maintain retention, backup, and deletion policies compliant with personal data requirements.
- Manage schema/topic ACLs and audit administrative actions.

Messages can persist in brokers, replication logs, DLQs, and backups far longer than an RPC. Minimal payload design and retention policies must account for the entire data lifecycle.

## 20. Testing Messaging in Spring

A test suite should be organized by purpose:

1. Unit tests for handlers: verify business logic with valid and invalid events.
2. Serialization/contract tests: producers and consumers use compatible schemas.
3. Integration tests with a real broker or Testcontainers: publish, consume, ack, and retry.
4. Idempotency tests: deliver the same event twice and produce only one business effect.
5. Failure-window tests: consumer crashes after DB commit before ack; message is redelivered safely.
6. Outbox tests: transaction commit creates outbox row; relay publishes and handles duplicate publishes.
7. DLQ tests: poison messages route to the right destination after the retry policy.
8. Ordering tests: messages with the same aggregate key are processed in the contract-required order.

Do not rely solely on mocked KafkaTemplate/RabbitTemplate to conclude broker delivery guarantees work. Mocks are useful for unit tests, but they do not test the broker, wire serialization, offsets/acks, routing, or redelivery.

## 21. Common Mistakes When Choosing Messaging

| Mistake | Consequence | Mitigation |
| --- | --- | --- |
| Using messaging for queries needing immediate responses | Caller lacks the result to proceed | Use gRPC/REST or design an async operation with a status API. |
| Treating broker ack as consumer completion | Reports success prematurely | Distinguish publish acknowledgement from business completion. |
| Assuming end-to-end exactly-once | Side effects can still be duplicated | Use idempotency, inbox/outbox, and clear transaction boundaries. |
| Infinite retries or no backoff | Retry storms and growing backlog | Cap attempts, add backoff, and use DLQ. |
| Missing event IDs | Hard to deduplicate and trace | Assign unique event identifiers. |
| Omitting partition keys | Loses required ordering or creates hot partitions | Pick keys based on aggregates and throughput. |
| Consumer processing too many messages concurrently | Overloads DB and breaks ordering | Bound concurrency/queues. |
| Incompatible schema changes | Older consumers fail to parse/understand events | Version schemas and run contract tests. |
| Swallowing exceptions and acking | Drops messages even though business work did not finish | Let error handlers apply retry/recovery policies. |
| Not monitoring lag and DLQ | Slow or failing workflows go undetected | Measure event age, lag, retries, and DLQ. |

## 22. Decision Matrix

| Question | If the answer is "yes" | Direction to consider |
| --- | --- | --- |
| Does the caller need the result immediately within the same request? | Yes | gRPC or REST is usually appropriate. |
| Can the work be processed after the initial response? | Yes | Messaging is a strong candidate. |
| Is buffering needed when consumers are temporarily offline? | Yes | Choose a broker with appropriate durability. |
| Does one event need multiple independent consumers? | Yes | Topic/fan-out or multiple subscriptions. |
| Is event history replay needed? | Yes | Event log/stream retention has an advantage. |
| Is flexible queue routing needed for commands/work items? | Yes | Message broker queues/routing may fit. |
| Must duplicate side effects be prevented? | Yes | Design idempotency/inbox/outbox before enabling retries. |
| Is ordering per aggregate required? | Yes | Pick suitable partition/routing keys and concurrency. |

Messaging is only appropriate when the team accepts eventual consistency, operating a broker, managing schemas, and monitoring backlogs. If buffering or temporal decoupling is unnecessary, synchronous RPC may be simpler.

## 23. Hands-on Exercise

Design an order-creation flow in a Spring system:

1. The browser calls a REST API to create an order.
2. OrderService calls InventoryService over gRPC if immediate stock-check feedback is needed.
3. OrderService saves the order and OrderCreated event in the same transaction via an outbox.
4. The outbox relay publishes the Protobuf payload to a topic.
5. BillingService and NotificationService consume the event via Spring listeners.
6. Consumers use event_id for idempotency and avoid duplicate side effects.
7. Configure bounded retries, backoff, and a DLQ.
8. Choose order_id as the key to preserve event order for the same order.
9. Monitor publish acknowledgements, consumer lag, event age, processing duration, and DLQ.
10. Test consumer redelivery after database commit but before acknowledgement.

**Completion criteria:** clearly distinguishes which parts need synchronous gRPC versus messaging, defines delivery/retry/idempotency policies, ensures schema compatibility, and explains how to observe workflows when consumers are slow or failing.

## 24. Takeaways

- Messaging decouples producers and consumers in time, supporting buffering, fan-out, and background processing.
- Async gRPC is still RPC; it does not inherently provide durable queues or replay.
- Commands request actions; events state facts that have occurred.
- Broker acknowledgement does not prove the consumer completed business work.
- At-least-once can deliver duplicates; idempotent consumers and inboxes protect side effects.
- Transactional outbox prevents lost events between database commit and publish; consumers must still tolerate duplicates.
- Ordering usually holds only within a queue/partition/key scope, not system-wide.
- Retries need limits, backoff, and DLQs; poison messages should not be retried forever.
- Schemas must stay compatible when producers and consumers deploy out of sync.
- Monitor event age, consumer lag, retries, DLQs, and outbox backlog to know whether workflows finish on time.
- Use gRPC for synchronous interactions needing responses; use messaging for deferred work requiring temporal decoupling.

Choose messaging for asynchronous communication when the system needs to decouple producers from consumers, absorb load, and reliably process background work; combine it with gRPC for steps requiring synchronous results so each interaction uses the right semantics.

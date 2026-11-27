# Two Independent Groups Receiving Events: Payment and Notification

In an e-commerce system, when an order is created, multiple components need to react to the same event. The **Payment Service** needs to process payment; the **Notification Service** needs to send an email, SMS, or in-app notification. Both workflows start from `OrderCreated`, yet they have different goals, processing speeds, failure modes, and deployment lifecycles. If one side is temporarily unavailable, the other must still continue processing.

This exercise belongs to the **End-to-End Exercise** chapter of the `SPRING_CLOUD_STREAM` module. We use Spring Cloud Stream with the `Supplier`/`Function`/`Consumer` functional model, bindings, and binders for Kafka, RabbitMQ, or Pulsar to build two independent consumer groups on the same destination. The exercise walks through the event contract, producer, binding configuration, consumer implementations, retry/DLQ, idempotency, observability, and end-to-end testing.

## 1. Business Problem

When a customer successfully places an order, the Order Service emits an event:

```text
OrderCreated
    |
    +----> Payment Service
    |         - Validate payment request
    |         - Send authorize/charge command to payment provider
    |         - Record payment outcome
    |
    +----> Notification Service
              - Send order-received confirmation email
              - Send push notification if enabled by customer
              - Record notification delivery status
```

The two consumers have different requirements:

| Attribute | Payment Service | Notification Service |
|---|---|---|
| Consumer group | `payment-service` | `notification-service` |
| Input destination | `orders.created` | `orders.created` |
| Responsibility | Process payment | Send order confirmation notification |
| Side effects outside broker | Payment provider, payment database | Email/SMS/push provider, notification database |
| Retry policy | Based on payment provider errors and transaction state | Based on notification provider errors |
| DLQ | Dedicated payment DLQ | Dedicated notification DLQ |
| Processing speed | Depends on payment provider and transaction rate limits | Depends on email/SMS/push provider |
| Scaling | Based on backlog and payment provider limits | Based on backlog and notification provider limits |
| Idempotency | By `eventId` and payment operation key | By `eventId` and notification delivery key |

The key requirement is that each consumer group must receive a **logical copy of the same event**. The two groups do not split messages 50/50 between them. Only instances within the same group share work.

## 2. Distinguishing Two Independent Groups from Two Consumers in the Same Group

This is the core concept of the exercise.

```text
                    orders.created
                           |
                    Event: OrderCreated
                           |
                +----------+----------+
                |                     |
                v                     v
       group=payment-service   group=notification-service
                |                     |
          +-----+-----+         +-----+-----+
          |           |         |           |
          v           v         v           v
       Payment 1   Payment 2  Notify 1   Notify 2
```

In this diagram:

- `Payment 1` and `Payment 2` are instances belonging to `payment-service`; they compete to process messages for the payment group.
- `Notify 1` and `Notify 2` are instances belonging to `notification-service`; they compete to process messages for the notification group.
- Both groups receive `OrderCreated`.
- Processing a message in the payment group does not remove the copy needed by the notification group.

If both bindings are configured with the same `group: order-processing`, instances end up in a single competing group. An event would be delivered to either Payment or Notification depending on distribution, rather than both receiving it. That is an incorrect configuration for this exercise's requirements.

## 3. Consumer Groups in Spring Cloud Stream

Each input binding can declare `spring.cloud.stream.bindings.<bindingName>.group`. All consumer groups subscribed to the same destination receive a copy of published data; within each group, only one member receives a specific message. This combines the publish-subscribe model with competing consumers.

| Configuration | Meaning |
|---|---|
| `destination: orders.created` | Event source read by the binding |
| `group: payment-service` | Identifier for the payment processing group |
| `group: notification-service` | Identifier for the notification processing group |
| Two distinct groups | Each group tracks consumption progress independently |
| Multiple instances in same group | Balances message load within that group |
| No group declared | Binder may create an anonymous group; unsuitable when durable subscriptions across restarts are needed |

In production, always configure stable group names for consumers that must resume processing after all instances pause. Never use a Pod name, hostname, or fresh UUID per deployment as the group name; doing so creates a new group and can cause messages to be replayed from the initial offset/position.

## 4. The `OrderCreated` Event Contract

Both services must agree on the event schema. An event describes what happened, not an internal command instructing another service to invoke a specific function.

Example JSON:

```json
{
  "eventId": "evt-20261124-000042",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T09:30:00Z",
  "orderId": "ord-100042",
  "customerId": "cus-9008",
  "currency": "VND",
  "totalAmount": 1250000,
  "paymentMethod": "CARD",
  "notificationPreference": {
    "email": true,
    "push": true
  }
}
```

Field meanings:

| Field | Purpose |
|---|---|
| `eventId` | Stable identifier for deduplication in each consumer group |
| `eventType` | Indicates the event type |
| `schemaVersion` | Supports schema evolution |
| `occurredAt` | Timestamp when the business event was created, used for audit and latency |
| `orderId` | Domain business key of the order |
| `customerId` | Customer reference; protect personal data |
| `currency` | Currency unit of the monetary amount |
| `totalAmount` | Total amount in the smallest unit of the currency per contract convention |
| `paymentMethod` | Selected payment method |
| `notificationPreference` | Notification preferences captured at order creation time |

Do not emit full card numbers, CVVs, payment tokens, or customer authentication credentials in events. The Payment Service should retrieve payment credentials from a securely stored vault or provider token. The Notification Service should only use verified contact addresses and adhere to consent policies.

## 5. Creating Shared Java Data Types

In this learning example, both consumers can use the same record definitions:

```java
import java.time.Instant;

public record OrderCreated(
        String eventId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String orderId,
        String customerId,
        String currency,
        long totalAmount,
        String paymentMethod,
        NotificationPreference notificationPreference) {
}

public record NotificationPreference(
        boolean email,
        boolean push) {
}
```

In a multi-service system, you do not necessarily have to package Order Service's Java classes into a shared JAR for every consumer. Contracts can be managed with JSON Schema, Avro, or Protobuf, with each service generating its own models. What matters is schema compatibility and clearly published field-change rules.

## 6. Producer Publishing One Event to a Shared Destination

The Order Service emits `OrderCreated` once. Spring Cloud Stream's `StreamBridge` fits cases where the publisher is triggered by a request or business transaction:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send(
                "orders-out-0",
                MessageBuilder.withPayload(event)
                        .setHeader("eventId", event.eventId())
                        .build());
    }
}
```

Output binding declaration:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
```

The producer does not need to send one copy to `payment-service` and another to `notification-service`. The broker and binder fan out across the two consumer groups. This avoids having the producer manage two send paths and deal with partial failure where sending succeeds for payment but fails for notification.

`StreamBridge.send()` returns the result of sending through the binding/channel; do not interpret that boolean as proof that payment has been processed, email has been sent, or every consumer has received it. To avoid losing events when Order Service commits to the database and crashes before publishing, see the Transactional Outbox section below.

## 7. Two Consumer Functions in Spring Cloud Stream

Declare two independent beans, each with its own input binding:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderEventConsumers {

    @Bean
    Consumer<OrderCreated> processPayment(PaymentService paymentService) {
        return event -> paymentService.processOrderCreated(event);
    }

    @Bean
    Consumer<OrderCreated> sendNotification(
            NotificationService notificationService) {
        return event -> notificationService.sendOrderReceived(event);
    }
}
```

`PaymentService` and `NotificationService` are domain services implemented by the application. In this example, each consumer returns after the required work has completed or its processing state has been durably persisted. If processing fails, the exception must propagate outward according to the chosen error-handling policy so the binder can retry or route the message to a DLQ.

Enable both functions in the application:

```yaml
spring:
  cloud:
    function:
      definition: processPayment;sendNotification
```

The semicolon `;` lists two independent functions. Do not use function composition `processPayment|sendNotification` here. Composition feeds the output of the first function as the input to the second, meaning notification would depend on payment's output instead of both acting as independent consumers receiving `OrderCreated`.

## 8. Configuring Two Input Bindings with Separate Groups

This is the most critical configuration section:

```yaml
spring:
  cloud:
    function:
      definition: processPayment;sendNotification
    stream:
      bindings:
        processPayment-in-0:
          destination: orders.created
          group: payment-service
          content-type: application/json
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
            backOffMaxInterval: 10000

        sendNotification-in-0:
          destination: orders.created
          group: notification-service
          content-type: application/json
          consumer:
            maxAttempts: 5
            backOffInitialInterval: 2000
            backOffMultiplier: 2.0
            backOffMaxInterval: 30000
```

Both bindings share the same `destination` but specify different `group` values. This configures fan-out via consumer groups. Separate retry policies are also declared: payment failures and notification failures do not necessarily share the same recovery window.

| Binding | Function | Destination | Group |
|---|---|---|---|
| `processPayment-in-0` | `processPayment` | `orders.created` | `payment-service` |
| `sendNotification-in-0` | `sendNotification` | `orders.created` | `notification-service` |

If deployed as two separate applications, each application only declares its own function and binding while keeping the corresponding destination and group. There is no need to declare the other service's function in the current application.

## 9. Single Application or Two Separate Deployments?

Both consumers can be declared inside one Spring Boot application to demonstrate the pattern. In production, the two services should usually have independent lifecycles and resources:

```text
                     orders.created
                           |
                +----------+----------+
                |                     |
                v                     v
          Payment Deployment     Notification Deployment
          group=payment-service  group=notification-service
          2..8 replicas           1..5 replicas
          payment DB/provider    notification DB/provider
```

| Criterion | Single application | Two separate applications |
|---|---|---|
| Deployment unit | Single artifact | Separate artifact per service |
| Scaling | Scales the whole process containing both consumers | Scales each group by its own backlog |
| Startup failure | One broken context can impact both | Can start independently |
| Resources | Shares CPU, heap, connection pools | Isolated resource limits |
| Releases | Coupled release cadence | Independent releases |
| Security | One identity may accumulate broad permissions | Least-privilege permissions per service |
| Observability | Shared process, requires binding-level filtering | Clear per-service metrics and logs |

When running in the same JVM, consumer groups remain independent on the broker, but **the process failure domain is not fully isolated**. An OOM, global misconfiguration, or shutdown stops both consumers. Split deployments when payment and notification require different SLAs, scaling, or access controls.

## 10. Kafka: Two Consumer Groups Reading the Same Topic

With the Kafka Binder, each consumer group maps to a separate Kafka consumer group. The two groups maintain independent committed offsets on the same topic:

```text
Kafka topic: orders.created (6 partitions)
                  |
          +-------+-------+
          |               |
          v               v
  group payment-service   group notification-service
    P0..P5 assigned         P0..P5 assigned
      |       |               |       |
   Payment instances       Notification instances
```

When a record is published to partition P2:

- Group `payment-service` reads the record at its own group offset.
- Group `notification-service` also reads the record at its own group offset.
- Payment may commit offsets faster than notification; that does not cause notification to miss records.
- If the payment group stops, the notification group continues processing.
- When the payment group restarts, it resumes from its committed offset according to Kafka policy and retention.

For example, both groups can have distinct Kafka binder consumer properties:

```yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processPayment-in-0:
            consumer:
              startOffset: earliest
              enableDlq: true
              dlqName: orders.created.payment.dlt
          sendNotification-in-0:
            consumer:
              startOffset: earliest
              enableDlq: true
              dlqName: orders.created.notification.dlt
```

These are **Kafka Binder extended consumer properties**, not generic properties across all binders. `startOffset` only takes effect when a group has no committed offset yet; it does not rewind a group that already has committed offsets. To replay already-processed data, you need a dedicated offset/replay procedure rather than merely changing `startOffset`.

A Kafka topic must have enough partitions for the planned concurrency of **each group**. Two groups reading the same topic do not divide partitions between them: each group gets assigned the full set of partitions, while instances within a group divide those partitions.

## 11. RabbitMQ: One Exchange, Two Queues by Group

By default, the RabbitMQ Binder maps a destination to a topic exchange. For named consumer groups, the binder creates a dedicated queue per group and binds each queue to the exchange. Default queue names typically follow:

```text
<destination>.<group>

orders.created.payment-service
orders.created.notification-service
```

Publishing to the `orders.created` exchange routes the message to both queues. Within each queue, instances of the same group compete for messages.

```text
                   exchange orders.created
                         |
                  routing key: #
                   /           \
                  /             \
                 v               v
  queue orders.created.       queue orders.created.
       payment-service            notification-service
          |                              |
      Payment 1/2                   Notification 1/2
```

**Key difference from Kafka:** a RabbitMQ exchange does not retain message history for a queue created later. If the `notification-service` queue does not exist when the producer publishes, old messages will not retroactively appear in that queue later. For systems that must receive every event even while a service is temporarily stopped, ensure durable queues/groups are pre-provisioned with appropriate retention policies.

The RabbitMQ Binder supports `requiredGroups` on the output binding to provision queues for groups that must receive messages even if their consumers are not running yet at publish time. Example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          producer:
            requiredGroups:
              - payment-service
              - notification-service
```

Verify this property against your RabbitMQ Binder version and topology. If infrastructure manages queues/exchanges via IaC, verify names, durability, bindings, and permissions instead of letting applications declare duplicate resources.

## 12. Pulsar: Two Independent Subscriptions

In Apache Pulsar, a topic can have multiple subscriptions. Each subscription maintains its own cursor and acknowledgment state. Therefore, two Spring Cloud Stream consumer groups map to two distinct subscriptions:

```text
Topic: persistent://acme/orders/orders.created
                         |
              +----------+----------+
              |                     |
              v                     v
 subscription payment-service   subscription notification-service
              |                     |
        Payment consumers      Notification consumers
```

When one subscription acknowledges a message, the other subscription's cursor does not advance automatically. If payment has processed an event while notification has not, the notification subscription retains its backlog.

In Spring Cloud Stream configuration, still set distinct `group` values on the two input bindings as shown in section 8. The Pulsar Binder uses Spring for Apache Pulsar components to create consumer bindings; in operations, verify the actual subscription name, subscription type, and initial position using the binder/cluster configuration of the version in use. Do not infer subscription names solely from bean names.

Subscription type governs how instances within **a single subscription** share messages:

| Subscription type | Primary behavior | When appropriate |
|---|---|---|
| `Exclusive` | Single active consumer | Simple flows not requiring concurrent consumers |
| `Failover` | Active/standby; on partitioned topics, partition ownership can be distributed | Need failover and per-partition ordering semantics |
| `Shared` | Multiple consumers receive messages concurrently without global ordering guarantees | Throughput and independent message processing |
| `Key_Shared` | Distributes by key, keeping the same key on the same consumer per Pulsar semantics | Parallelism across keys with per-key ordering |

The payment and notification subscriptions are two independent streams. Subscription type only determines load sharing inside each stream.

## 13. Comparing Fan-Out Across the Three Binders

| Spring Cloud Stream concept | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Destination | Topic | Exchange/destination | Topic |
| Consumer group | Kafka consumer group | Queue tied to group | Consumer binding subscription |
| Independent copy | Each group has its own offsets | Each group has its own queue | Each subscription has its own cursor |
| Instances in same group | Share partitions | Compete on queue | Share subscription per subscription type |
| Data while service is stopped | Topic retains per retention policy | Durable queue retains messages if provisioned | Durable subscription retains backlog per retention/policy |
| What to verify | Offsets, partitions, retention | Queue existence, durability, DLX/routing | Subscription name/type, cursor, retention |

Spring Cloud Stream standardizes the concepts of `destination` and `group`, but each binder has a distinct broker model. Never apply `kafka.bindings.*` properties to RabbitMQ/Pulsar or assume a RabbitMQ queue created afterward will receive previously published messages.

## 14. What Happens When the Payment Service Stops?

Suppose both groups are running, and then the Payment Service loses database connectivity for 10 minutes:

```text
orders.created
       |
       +--> payment-service
       |       - Retries per policy
       |       - Lag/backlog grows
       |       - Notification group is not blocked
       |
       +--> notification-service
               - Continues reading
               - Sends order-received notifications
               - Commits/acks independently
```

Expected behavior:

1. Notification Service continues sending order-received notifications as long as its dependencies are healthy.
2. Payment Service does not mark transactions successful without a confirmed result from the payment provider.
3. Messages for the payment group remain retained per broker semantics and are not acked/committed as successful until safely handled.
4. When the database/payment provider recovers, the payment group processes the backlog.
5. Notifications are not sent again just because the payment group retries the same `OrderCreated` event.

If both consumers run inside the same process, binding errors can affect the process lifecycle. Split deployments if operational requirements demand that notifications continue even when the payment application crashes.

## 15. Independent Retry Policies per Group

Payment and Notification depend on different external services. Therefore, retry counts and backoff intervals can differ:

| Error | Payment | Notification |
|---|---|---|
| Short timeout | Bounded retry; check transaction status before retrying | Bounded retry with backoff |
| HTTP 429 from provider | Respect `Retry-After`, apply rate limiting | Respect email/SMS provider quotas |
| Expired credentials | Halt/throttle processing, alert on configuration | Halt/throttle processing, alert on configuration |
| Invalid event schema | Route to DLQ and investigate contract | Route to separate DLQ and investigate contract |
| Duplicate event | Idempotency by payment operation | Idempotency by notification delivery |
| Permanent failure | Quarantine and handle via business workflow | Quarantine; do not send repeatedly forever |

The shared configuration example in section 8 set different `maxAttempts`. `maxAttempts` includes the initial processing attempt in common consumer configuration; exact retry/backoff behavior also depends on the binder, imperative vs. reactive processing, and custom error handlers. DLQs must be enabled and declared per binder.

## 16. Kafka: Separate DLQs per Consumer Group

The two groups can use separate DLTs so the payment and notification teams can triage independently:

```yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processPayment-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.payment.dlt
          sendNotification-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.notification.dlt
```

The Kafka Binder requires an explicit consumer group for DLQ support. The DLT must also be provisioned with appropriate partition counts, retention, and write permissions. When one group fails, records follow that group's DLT policy; the other group keeps its own offsets.

Do not share one consumer group across both functions and expect `dlqName` to separate business workflows. Binding names and groups must be verified in logs/runtime configuration; DLT records should preserve `eventId`, source topic, partition/offset, group, and failure cause for traceability.

## 17. RabbitMQ: Separate DLQs per Queue/Group

With the RabbitMQ Binder, each group has its own queue, so separate DLQs can be configured per binding:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processPayment-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
          sendNotification-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
```

Actual queue/DLQ names created by the binder depend on destination, group, and naming properties. Verify the actual queues on the broker; do not guess DLQ names solely from function names. `requeueRejected: false` prevents failed deliveries from looping back to the main queue via rejection, while `autoBindDlq` declares the DLX/DLQ when the binder is permitted to provision topology.

If the Payment queue fails continuously, the payment DLQ grows; the notification queue does not lose messages to the payment consumer. However, both queues can still be jointly affected if the RabbitMQ cluster, vhost, disk, or network experiences an outage.

## 18. Pulsar: Separate Subscription Backlogs and DLQs

Pulsar tracks acknowledgments per subscription. When the payment subscription encounters errors, its backlog grows while the notification subscription can still advance its cursor. Monitor:

- Full topic name, e.g., `persistent://acme/orders/orders.created`.
- Subscription names corresponding to payment and notification.
- Subscription type (`Shared`, `Key_Shared`, `Failover`, or `Exclusive`).
- Backlog, unacknowledged messages, and redeliveries per subscription.
- Retry letter topics and dead-letter topics for each group.
- Read permissions on the main topic and publish permissions on retry/DLQ topics.

The Pulsar Binder uses Spring for Apache Pulsar consumer configuration; exact retry/DLQ settings depend on the binder version and exposed APIs. Do not copy Kafka `enableDlq` or RabbitMQ `autoBindDlq` properties to Pulsar. Verify the consumer builder/extended binding properties for your release and test a failing message in an integration environment.

## 19. Idempotency for the Payment Service

Payment is a high-risk side effect: the same `OrderCreated` event can be redelivered after a timeout, process crash, or incomplete ack/commit. If every delivery triggers a new charge, customers could be charged multiple times.

A payment operation needs a stable idempotency key, such as `payment:{orderId}:initial`. Illustrative flow:

```text
Receive OrderCreated(eventId, orderId)
          |
          v
Check processed event / payment operation
          |
    +-----+------+
    |            |
 already done   new operation
    |            |
    v            v
 return result   reserve idempotency key
                 call provider with same key
                 persist provider result
                 mark event processed
```

Example tables:

```sql
CREATE TABLE payment_operation (
    order_id          VARCHAR(100) PRIMARY KEY,
    event_id          VARCHAR(100) NOT NULL,
    idempotency_key   VARCHAR(160) NOT NULL UNIQUE,
    status            VARCHAR(32) NOT NULL,
    provider_reference VARCHAR(160),
    updated_at        TIMESTAMP NOT NULL
);

CREATE TABLE payment_consumed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

This is an illustrative schema; adjust column types, transactions, and unique constraints for your database. If the provider supports idempotency keys, pass the same key when retrying a payment operation. If a timeout occurs after the provider already charged the card but before the response returned, query the status by key/reference before creating a new transaction.

Do not treat the `eventId` of a newly replayed message as a new payment operation if it represents the same original business event. During replay, preserve `originalEventId` and the original idempotency key.

## 20. Idempotency for the Notification Service

Notifications can also be redelivered. Sending the same email twice hurts user experience, and duplicate SMS messages incur extra cost. Construct a delivery key by notification type and recipient:

```text
notificationKey = eventId + channel + recipientId + templateVersion
```

Example table:

```sql
CREATE TABLE notification_delivery (
    notification_key VARCHAR(300) PRIMARY KEY,
    event_id          VARCHAR(100) NOT NULL,
    channel           VARCHAR(24) NOT NULL,
    recipient_id      VARCHAR(100) NOT NULL,
    status            VARCHAR(32) NOT NULL,
    provider_reference VARCHAR(160),
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL
);
```

The Notification Service checks the delivery key before sending. If already `SENT`, redelivery simply confirms completion without calling the provider again. If the provider supports idempotency, pass the same delivery key. If the provider does not support it, handle the uncertainty window where a request timed out even though the provider may have delivered it; an `UNKNOWN` status requires reconciliation rather than blind retries.

Payment and notification maintain **two separate deduplication ledgers**. Payment recording an `eventId` does not allow notification to skip that event; each group must persist its own processing state.

## 21. Ack/Commit After Side Effects Are Safe

A consumer should not treat a message as complete before required side effects are durably persisted. Payment Service example:

```text
Broker delivers OrderCreated
       |
       v
DB transaction: create/reserve payment operation
       |
       v
Call payment provider with idempotency key
       |
       v
Persist result / reconcile uncertain result
       |
       v
Handler completes -> binder acknowledges/commits per configuration
```

In practice, calling an external payment provider cannot participate in the database's ACID transaction. You can use a `PENDING` state, a workflow/saga, and a reconciliation job. If the process stops after the provider charged successfully but before the database recorded the result, redelivery must query the provider by idempotency key/reference.

The Notification Service also needs to distinguish `SENT`, `FAILED_RETRYABLE`, `FAILED_PERMANENT`, and `UNKNOWN`. Never acknowledge an event merely because it was submitted to an in-memory executor; if the process dies before the executor runs, work can be lost.

## 22. Transactional Outbox in the Order Service

There is a failure window on the producer side:

```text
1. Order Service commits order to DB.
2. Process crashes before publishing OrderCreated.
3. Order exists, but neither consumer receives the event.
```

The Transactional Outbox solves this by writing both the order and the outbox record within the same database transaction:

```sql
BEGIN;

INSERT INTO orders(order_id, customer_id, status, total_amount)
VALUES ('ord-100042', 'cus-9008', 'CREATED', 1250000);

INSERT INTO outbox_event(event_id, aggregate_id, event_type, payload, status)
VALUES ('evt-20261124-000042', 'ord-100042', 'OrderCreated', :json, 'NEW');

COMMIT;
```

An outbox publisher reads `NEW` records, sends them to `orders.created` using Spring Cloud Stream/`StreamBridge`, and updates the delivery status. If the publisher crashes after the broker receives the event but before marking `SENT`, it may resend the event; hence both consumers must still be idempotent by `eventId`.

An outbox prevents losing events between database commit and publish, but it does not turn the entire producer → broker → two databases → payment provider/email provider chain into a single distributed transaction.

## 23. Two Independent Groups Do Not Imply Ordering Between Them

Kafka may write `OrderCreated` to a single partition; both groups read the same log, yet their progress and processing times differ. RabbitMQ has two separate queues; consumers on the payment queue may outpace the notification queue. Pulsar has two independent subscription cursors.

Therefore, never assume:

```text
Payment finishes first -> Notification definitely processes afterward
```

Both handlers can execute concurrently. If notification needs to know the payment outcome, emit a separate outcome event such as `PaymentAuthorized` or `PaymentDeclined`, and let the notification workflow handle that event. Do not infer payment success just because both read `OrderCreated`.

If business logic requires sending a "payment confirmed" email, the trigger should be `PaymentAuthorized`, not `OrderCreated`. If it only sends an "order received" email, `OrderCreated` is the appropriate event.

## 24. Ordering by `orderId` Within Each Group

The two consumer groups can have independent ordering and processing rates. If a group needs ordering for the same order:

- With Kafka, the producer sets the record key to `orderId`; events with the same key land in the same partition. Each group receives its own partition assignment.
- With RabbitMQ, design routing keys/queue partitioning carefully; multiple consumers on the same queue can finish out of order if processing asynchronously.
- With Pulsar, choose an appropriate subscription type and message key; `Key_Shared` can preserve key-based distribution, though batching semantics must be checked.

In this example, `OrderCreated` can use `orderId` as its key. Payment and Notification still receive independent copies because the key only controls partitioning/routing within a destination, rather than merging two groups into one.

## 25. Schema Evolution When Two Groups Deploy at Different Cadences

Payment and Notification may release on different schedules. When Order Service adds fields, events must preserve compatibility:

| Change | Risk | Safe rule |
|---|---|---|
| Add optional field | Older consumers do not recognize field | Provide clear default/null semantics |
| Rename field | Older consumers cannot read it | Add new field while keeping old field during transition |
| Change type of `totalAmount` | Deserialization failure or precision loss | Version the schema and migrate under control |
| Remove field | Older consumers relying on it break | Remove only after all consumers have upgraded |
| Change field meaning | Deserialization succeeds but business logic breaks | Introduce a new field, event type, or schema version |

Do not leak payment-specific internals (such as a provider authorization token) into a schema shared with notification. An event contract should contain only data needed by subscribers and follow data-minimization principles.

## 26. Independent Retry and DLQ per Service

Each consumer group can define its own retry/DLQ policy:

```text
orders.created
     |
     +--> payment-service
     |       retry policy P
     |       orders.created.payment.dlt
     |
     +--> notification-service
             retry policy N
             orders.created.notification.dlt
```

A failing payment event should not force Notification Service to retry the same message if notification already succeeded. Conversely, an email provider outage should not cause Payment Service to re-invoke the payment provider.

| Consumer | Appropriate for retry | DLQ used for |
|---|---|---|
| Payment | Transient timeouts, provider 429/503, temporary DB errors | Malformed event schema, unprocessable state, retries exhausted |
| Notification | Email/SMS/push timeouts, provider throttling | Invalid recipient address, template/schema error, retries exhausted |

Do not retry permanent errors with unbounded backoff. Use bounded retries, exponential backoff, jitter, and parking-lot/triage workflows. When replaying, preserve `originalEventId` so duplicate payments or notifications are not triggered.

## 27. Kafka: Per-Binding Retry/DLT

Kafka Binder example for both consumer groups:

```yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processPayment-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.payment.dlt
          sendNotification-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.notification.dlt
```

These are Kafka Binder extended properties. Both input bindings need explicit groups. The DLT must have appropriate partitions and write permissions; for partitioned topics, verify DLT partition routing. If the app registers a custom error handler, check whether that handler overrides the binder's DLQ path.

When the payment DLT grows, only the payment workflow requires investigation/replay. The notification group has its own committed offsets and will not automatically replay just because messages landed in the payment DLT.

## 28. RabbitMQ: Per-Group Queue and DLQ

RabbitMQ Binder example:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processPayment-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
          sendNotification-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
```

With named groups, the RabbitMQ Binder provisions a separate queue per group and binds it to the destination exchange. DLQ naming and routing depend on binder configuration. Verify the actual queues/exchanges in the target vhost, especially when using prefixes, partitioning, or IaC-provisioned queues.

If a queue uses Single Active Consumer, scaling out more instances does not add more active consumers to that queue. That affects throughput only for that group and does not disrupt the other group's queue.

## 29. Pulsar: Independent Subscription Types and Cursors

Pulsar maintains a cursor per subscription. Two subscriptions on the same topic can have different backlogs and processing speeds. Track stats per subscription, not only at the topic aggregate level.

If you choose `Shared`, multiple consumers in one subscription share messages without global ordering guarantees. If per-key ordering is required, consider `Key_Shared` and configure producer keys and batching accordingly. `Failover` suits active/standby or partitioned failover models; `Exclusive` allows only a single consumer.

Retry letter topics and dead-letter policies must be configured according to your actual Pulsar client/binder release. Separate retry/DLQ topic names for payment and notification so the two workflows do not share retry state. Verify ACLs for subscriptions and producers writing to retry/DLQ topics.

## 30. Scaling Independently by Backlog

The two groups can require different replica counts. For example:

| Metric | Payment | Notification |
|---|---:|---:|
| Current backlog | 18,000 | 2,000 |
| Throughput per Pod (benchmark) | 120 events/s | 500 events/s |
| Desired replicas | 4 | 2 |
| Max replicas | 8 | 5 |
| Primary bottleneck | Payment provider quota | Email/SMS provider quota |

Do not use the same autoscaler or metric to scale both Deployments. In Kafka, each group has its own lag; a KEDA Kafka scaler must target the specific `consumerGroup` and topic. In RabbitMQ, the scaler must measure the specific group queue. In Pulsar, the scaler must measure the specific subscription. If payment backlog spikes, the notification Deployment does not need to scale merely because they share a destination.

Set max replicas based on downstream capacity. Scaling payment consumers too aggressively can exceed provider quotas and trigger 429 errors; scaling notification too aggressively can exhaust email quotas or hit rate limits.

## 31. Security and Least-Privilege Access

The two services do not necessarily need the same broker permissions or external credentials:

| Component | Required permissions |
|---|---|
| Order Service producer | Produce to `orders.created` |
| Payment Service consumer | Consume from payment destination/group; publish payment results if applicable |
| Notification Service consumer | Consume from notification destination/group |
| Payment DLQ worker | Read payment DLT and replay via authorized process |
| Notification DLQ worker | Read notification DLT and replay via authorized process |

Do not grant Notification Service read access to the payment database or payment provider secrets unnecessarily. Do not grant Payment Service access to email/SMS tokens. With Kafka, configure ACLs per topic/group; with RabbitMQ, restrict vhost/exchange/queue permissions; with Pulsar, restrict tenant/namespace/topic and roles. Scaler/monitoring credentials should also be separated from runtime consumer credentials.

## 32. Observing Group-Level State

Metrics should include `service`, `binding`, `destination`, `group`, and `outcome` labels at reasonable cardinality:

| Metric | Payment | Notification |
|---|---|---|
| Consumer lag/backlog | By `payment-service` | By `notification-service` |
| Processing rate | Payment operations/s | Notification deliveries/s |
| Processing latency | p50/p95/p99 authorize | p50/p95/p99 delivery |
| Retry count | Payment retries | Notification retries |
| DLQ count | Payment DLT | Notification DLT |
| Duplicate skipped | Payment idempotency | Notification idempotency |
| Error rate | Provider/DB/business | Email/SMS/push/template |
| Oldest event age | Age of oldest unprocessed event | Age of oldest unprocessed event |

A single topic-wide dashboard is insufficient: payment might be lagging by 20 minutes while notification lag is 0. Alert per group so the right service team responds.

## 33. Unit Testing Each Consumer

Unit tests should verify business logic and idempotency independently:

```java
@Test
void paymentConsumerUsesOrderIdempotency() {
    OrderCreated event = sampleOrderCreated();

    paymentService.processOrderCreated(event);

    verify(paymentGateway).authorize(
            eq(event.orderId()),
            eq("payment:" + event.orderId() + ":initial"));
}

@Test
void notificationConsumerUsesDeliveryKey() {
    OrderCreated event = sampleOrderCreated();

    notificationService.sendOrderReceived(event);

    verify(notificationGateway).send(
            eq(event.customerId()),
            eq("order-received"),
            contains(event.eventId()));
}
```

These are illustrative examples; method signatures and mock setups must match your application's actual interfaces. Unit tests do not prove broker fan-out or independent offsets/subscriptions.

## 34. Test Binder: Checking Wiring and Payloads

The Spring Cloud Stream Test Binder sends messages to input destinations and inspects outputs within the test context. It is useful for verifying function binding and payload/header conversion, but it does not fully emulate broker consumer groups.

Appropriate checks:

- `processPayment-in-0` receives `OrderCreated` with the expected content type.
- `sendNotification-in-0` receives the same schema.
- Consumers invoke the expected domain services.
- Functions emit result events (if any) to the expected destination.
- Exceptions are observed per test configuration.

Do not rely on the Test Binder as sole proof that Kafka maintains two group offsets, RabbitMQ creates two durable queues, or Pulsar creates two independent subscriptions. Integration tests against a real broker or Testcontainers are required.

## 35. Integration Test: Proving Both Groups Receive One Event

Minimal scenario with a real broker:

1. Start a Kafka/RabbitMQ/Pulsar test broker.
2. Start the Payment consumer with group `payment-service`.
3. Start the Notification consumer with group `notification-service`.
4. Publish exactly one `OrderCreated` event with a unique `eventId`.
5. Wait for the payment audit log to record `eventId`.
6. Wait for the notification audit log to record the same `eventId`.
7. Verify each group completed exactly one successful execution.

Expected result:

```text
Published eventId: evt-test-001

Payment audit:
  evt-test-001 -> PROCESSED

Notification audit:
  evt-test-001 -> SENT
```

Do not only verify that two methods were invoked in the same JVM; verify actual broker routing/subscriptions so accidental shared-group misconfigurations are caught.

## 36. Integration Test: Multiple Instances in the Same Group

Run two Payment instances in `payment-service` and two Notification instances in `notification-service`. Publish a batch of events with distinct IDs.

What to verify:

- Payment instances share the workload; under normal broker behavior, a single event is not processed concurrently by both instances in the same group.
- Notification instances share their workload independently.
- Every event is logically processed once in **each group**.
- Each event can be handled by one Payment instance and one Notification instance.
- Adding instances does not change the group name.

With Kafka, the number of consumers receiving partitions is bounded by the partition count within each group. With RabbitMQ, each group's queue has multiple competing consumers. With Pulsar, the subscription type determines load distribution within the subscription.

## 37. Integration Test: Stopping One Group

Critical scenario to demonstrate independence:

1. Start both services.
2. Stop all Payment instances (keeping the group/queue/subscription durable).
3. Publish 10 `OrderCreated` events.
4. Verify Notification Service processes all 10 events.
5. Verify payment backlog/lag grows or messages are retained per broker policy.
6. Restart Payment Service.
7. Verify Payment Service processes the queued events per offset/cursor/queue.
8. Verify Notification does not resend the 10 notifications just because Payment restarted.

With RabbitMQ, the payment queue must exist and be durable while the consumer is down; use pre-provisioning or `requiredGroups` if the producer keeps publishing. With Kafka/Pulsar, verify retention and subscription/offset policies cover the outage window.

## 38. Integration Test: Independent Failures and DLQs

Inject a failure only in the Payment Service, such as having a test payment provider return 503. Verify:

- The payment group retries according to its policy.
- The notification group continues processing successfully.
- After retries are exhausted, payment events move to the configured payment DLT/queue.
- Notification records no errors just because payment failed.
- When replaying payment events after the provider recovers, idempotency prevents duplicate transactions.

Repeat with an error only in the Notification Service (e.g., email provider returning 429). Payment must preserve accurate payment state while notification retries/DLQs independently.

## 39. Integration Test: Duplicate Delivery and Crash Windows

Brokers typically provide at-least-once delivery in many configurations. Test these crash windows:

| Crash point | Risk | Required outcome |
|---|---|---|
| Before DB write | Message is redelivered | Processes normally on redelivery |
| After DB commit, before ack/offset commit | Message is redelivered | Idempotency skips duplicate side effect |
| After provider success, before status write | Uncertain whether provider executed | Look up by idempotency key/reference |
| After publishing outcome event, before marking outbox sent | Outcome event may be republished | Downstream consumers deduplicate |
| After email provider success, before recording `SENT` | Email may be sent again | Provider idempotency or `UNKNOWN` state + reconciliation |

Do not claim end-to-end exactly-once semantics just because Kafka transactions or a binder's exactly-once setting is enabled. External databases and payment/email providers require their own idempotency and reconciliation mechanisms.

## 40. Monitoring Lag and Backlog Independently

Example snapshot on a dashboard:

| Metric | `payment-service` | `notification-service` |
|---|---:|---:|
| Backlog | 12,500 | 120 |
| Processing rate | 150 events/s | 450 events/s |
| Error rate | 8% | 0.2% |
| Retry rate | 7% | 0.1% |
| Oldest event age | 95 seconds | 2 seconds |
| Current replicas | 4 | 2 |

From these numbers, only Payment Service requires deep investigation. Adding Notification replicas will not resolve the payment backlog. Before scaling payment replicas, check payment provider quotas, database capacity, partition assignments, and error rates.

With Kafka, read lag per consumer group. With RabbitMQ, read queue depth for each group's queue and distinguish ready vs. unacknowledged messages. With Pulsar, read backlog per subscription. Do not collapse these metrics into a single aggregate that hides group identity.

## 41. Common Troubleshooting Table

| Symptom | Possible cause | Resolution |
|---|---|---|
| Only Payment or Notification receives events | Both bindings share the same group or destination is misconfigured | Check distinct `group` values and binding names |
| Each event goes to only one service | Competing consumers in the same group | Configure separate group/subscription/queue per service |
| Notification misses events while stopped | RabbitMQ queue not provisioned/durable or insufficient retention | Pre-create queues, verify `requiredGroups`/durability |
| Restarting service replays many events | Group name changed or offset/subscription reset | Keep group stable, check initial offset/cursor |
| Payment charged twice | Missing idempotency key or reconciliation | Use stable operation keys and unique constraints |
| Email sent twice | Redelivery after provider success before state write | Delivery ledger, provider idempotency, or reconciliation |
| Payment backlog grows while notification is normal | Payment dependency slow or failing retries | Investigate payment provider/DB and group lag separately |
| Both stop together | Shared process or shared broker/cluster outage | Split deployments if failure isolation is needed; check broker |
| RabbitMQ creates a new anonymous queue every time | No group configured | Configure a durable group and verify queue provisioning |
| Extra Kafka consumers sit idle | Consumer/concurrency count exceeds partition count | Plan partition increase or reduce concurrency |
| Pulsar two services read same subscription | Duplicate subscription name/group configured | Use two independent subscriptions |
| Payment DLQ receives notification errors | Both bindings share a DLQ or binding name mismatch | Configure separate DLQs per input binding |

## 42. Step-by-Step End-to-End Exercise

Execute in a development or staging environment:

**Step 1 — Prepare destination and event contract.** Choose `orders.created`, define `OrderCreated`, generate a stable `eventId`, and agree on `schemaVersion`.

**Step 2 — Create the producer.** Order Service sends an event through output binding `orders-out-0`. If events must not be lost between DB commit and publish, implement an outbox.

**Step 3 — Create the Payment consumer.** Declare `Consumer<OrderCreated>` named `processPayment`, group `payment-service`, an idempotency key, and dedicated retry/DLQ settings.

**Step 4 — Create the Notification consumer.** Declare `Consumer<OrderCreated>` named `sendNotification`, group `notification-service`, a delivery key, and dedicated retry/DLQ settings.

**Step 5 — Configure two independent functions.** Set `spring.cloud.function.definition=processPayment;sendNotification` with both bindings pointing to the same destination but different groups.

**Step 6 — Test fan-out.** Publish one event and verify both services record the same `eventId`.

**Step 7 — Test scaling.** Run multiple instances in each group, verify load sharing within each group, and confirm no cross-group copy loss.

**Step 8 — Test independent failures.** Disable the payment provider or simulate 503; notifications still send. Then simulate email provider 429; payments still process.

**Step 9 — Test stop/start.** Stop one service, keep publishing events, then restart it and verify the backlog is processed per broker policy.

**Step 10 — Test duplicates/replay.** Resend the same `eventId`; each group must prevent duplicate side effects using its own ledger.

## 43. Acceptance Criteria

This exercise is complete when you can demonstrate:

- A single `OrderCreated` event is published once to the shared destination.
- `payment-service` and `notification-service` use separate groups and receive the same event independently.
- Multiple instances in the same group share load without turning into unintended extra subscriptions.
- Stopping one service does not halt the other group while the broker remains healthy.
- Retries and DLQs are configured and observable independently per binding.
- Both Payment and Notification implement their own idempotency.
- Restarts, rebalances, and redeliveries do not trigger duplicate payments or notifications.
- Dashboards display lag/backlog, errors, retries, and DLQs per group.
- Schemas and access permissions expose only the data each service needs.
- Real-broker integration tests verify fan-out, pause/resume, and failure isolation.

## 44. Self-Check Questions

1. Why do two bindings with the same destination but different `group` values both receive a copy of an event?
2. If two consumers share the same group, how are messages distributed?
3. Why should you not put a Pod ID or a new UUID per deployment into a group name?
4. Does advancing the Kafka offset of `payment-service` advance the offset of `notification-service`?
5. How does RabbitMQ require a separate queue per group, and why must the queue exist before publishing if messages need to be retained?
6. What does an independent Pulsar subscription cursor mean when one service stops?
7. Why is `processPayment;sendNotification` different from `processPayment|sendNotification`?
8. If the payment provider already charged the card but the consumer crashes before acking, what mechanism prevents charging a second time?
9. If an email was sent but the database did not yet record `SENT`, how should the Notification Service handle that uncertain state?
10. Why do payment and notification need separate DLQs?
11. How do you prove that Notification Service still receives events when Payment Service is stopped?
12. Why is the Test Binder insufficient to prove that two Kafka consumer groups or two RabbitMQ queues are provisioned correctly?

## Conclusion

To let Payment Service and Notification Service receive the same `OrderCreated` event independently, publish one event to a shared destination and declare **two input bindings with two distinct consumer groups**. Instances within each group share work, while the two groups maintain independent progress, retries, DLQs, and scaling. Kafka achieves this with separate consumer groups and offsets, RabbitMQ with separate queues bound to an exchange, and Pulsar with separate subscriptions and cursors. Each service needs idempotency for its own side effects, handles at-least-once delivery, monitors its own backlog, and backs up fan-out and failure isolation with real-broker integration tests.

## References

- Spring Cloud Stream — Consumer Groups: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html
- Spring Cloud Stream — Functional Binding Names: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html
- Spring Cloud Stream — Binding Properties: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html
- Spring Cloud Stream — Producing and Consuming Messages / StreamBridge: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html
- Spring Cloud Stream — Kafka Binder Reference: https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html
- Spring Cloud Stream — RabbitMQ Binder Reference: https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html
- Spring Cloud Stream — Pulsar Binder: https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html
- Spring Cloud Stream — Test Binder: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html
- Apache Kafka — Consumer Groups and Documentation: https://kafka.apache.org/documentation/
- RabbitMQ — Exchanges and Queues: https://www.rabbitmq.com/docs/exchanges
- RabbitMQ — Consumers: https://www.rabbitmq.com/docs/consumers
- Apache Pulsar — Messaging and Subscriptions: https://pulsar.apache.org/docs/4.0.x/concepts-messaging/

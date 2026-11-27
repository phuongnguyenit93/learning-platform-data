# Routing Failed Events to DLQ and Controlled Replay

In a Spring Cloud Stream system, a consumer can encounter errors when processing events: a payment service becomes temporarily unreachable, the database exhausts connections, the payload is no longer schema-compatible, or business data violates rules. If messages keep getting redelivered indefinitely, a single failing event can monopolize consumers, grow backlogs, and impact healthy events. Conversely, if a message is dropped after an error, the system risks losing business effects.

A **Dead Letter Queue (DLQ)** is where failed messages are stored after exhausting the retry policy so operations teams can investigate, reconcile, and decide on next steps. In Kafka, a DLQ is typically a topic; in RabbitMQ, it is a queue bound via a dead-letter exchange (DLX); in Pulsar, it is a dead-letter topic. A DLQ isolates failing messages, but it does not automatically fix data, guarantee reprocessing, or provide a safe replay workflow on its own.

This exercise builds a complete workflow: classifying errors, bounded retries, routing events to a DLQ, preserving metadata for traceability, fixing root causes, selecting an approved subset of events to replay, controlling rate and ordering, preventing infinite loops, verifying outcomes, and moving unrecoverable events to a parking lot/quarantine. The main examples use Spring Cloud Stream with Kafka; subsequent sections compare configuration and replay on RabbitMQ and Pulsar.

This is an end-to-end exercise in the SPRING_CLOUD_STREAM module, where event-driven applications are built using `Supplier`, `Function`, and `Consumer` functions connected via bindings and binders to Kafka, RabbitMQ, or Pulsar. The DLQ/replay workflow must match the consumer group, partition/subscription model, message schema, retry/DLQ semantics, and delivery guarantees of the target broker.

## Exercise Objectives

Upon completing this exercise, you will be able to:

- Distinguish transient errors, data errors, and non-retryable business errors.
- Design bounded retries with backoff before routing messages to a DLQ.
- Enable DLQ for a named consumer group in the Kafka binder.
- Configure DLX/DLQ, republishing, and retries for the RabbitMQ binder.
- Understand Pulsar DLQ/retry topics and subscription-level acknowledgments.
- Preserve event ID, destination, partition/key, schema version, and error details.
- Build a dedicated replay worker with a cap on replay attempts.
- Route permanently failing events to a parking lot to prevent infinite loops.
- Replay in batches with filtering, rate limiting, and approved ordering.
- Protect side effects with idempotency and verify end-to-end outcomes.
- Operate, audit, and test failures during replay publishing.

## 1. Problem Context

Suppose the system receives `OrderCreated` events from topic `orders.created`. Function `processOrder` validates the event, persists the order, and emits `OrderAccepted`.

~~~text
Producer
   |
   v
orders.created
   |
   v
Spring Cloud Stream consumer group: order-service
   |
   +--> validate --> persist order --> publish OrderAccepted
   |
   +--> transient error: retry with backoff
   |
   +--> retries exhausted / non-retryable error: DLQ
                              |
                              v
                     Investigate and triage
                              |
                    +---------+---------+
                    |                   |
                 Fixed             Unfixable
                    |                   |
                    v                   v
            Controlled replay      Parking lot
                    |
                    v
             orders.created
                    |
                    v
           Consumer reprocesses
~~~

A DLQ is a quarantine zone. Replay is an intentional action to reintroduce events from quarantine back into a processing pipeline. Never treat a DLQ as an automatic retry queue: retries usually happen shortly according to policy, whereas a DLQ holds messages for human or recovery workflow decisions.

### 1.1. Concepts to Distinguish

| Concept | Purpose | Question to answer |
|---|---|---|
| Retry | Re-attempt an operation likely to succeed shortly | Can the error resolve itself within a brief window? |
| Retry topic/queue | Hold messages for a delay before the next attempt | Do we need delay without blocking consumer threads? |
| DLQ/DLT | Isolate messages that exceeded the retry policy | Which messages failed and why? |
| Parking lot/quarantine | Hold messages no longer eligible for automatic replay | Who will decide to fix or discard the message? |
| Replay | Re-emit an event stored in a DLQ/parking lot | Which events are allowed back, when, and how many times? |
| Reconciliation | Reconcile business state after an error | Did side effects already occur partially? |

Names like DLQ, DLT, retry topic, and parking lot vary by broker, yet the distinction in purpose must stay clear. A DLQ may serve for longer-term storage; a retry topic may be consumed automatically on schedule; a parking lot halts automatic loops once the replay budget is exhausted.

## 2. Classifying Errors Before Choosing Retries

Not every exception should be retried. Classify errors by recoverability and the impact of re-execution.

| Error category | Examples | Handling approach |
|---|---|---|
| Transient | Network timeout, HTTP 503, broker/database failover | Bounded retry with backoff |
| Throttling | HTTP 429, saturated connection pool | Retry after waiting, reduce rate |
| Data/serialization | Missing JSON fields, incompatible schema, corrupt payload | Route to DLQ early to fix data or code |
| Invalid business state | Order references nonexistent customer, disallowed state | Quarantine or request reconciliation |
| Authentication/authorization | Expired token, invalid credentials, ACL denial | Fix configuration/permissions; avoid tight retries |
| Code bug | Null handling, conversion bug, invariant failure | Hold messages in DLQ, release fix, then replay |
| Unknown cause | Unclassified exception | Very limited retries, then DLQ and investigate |

A `TimeoutException` may be transient, yet not every timeout is safe to retry. The server may have processed the request while the response was lost. If retrying triggers a duplicate charge or email, side effects repeat. Use idempotency keys on target systems and verify state before replaying.

### 2.1. Retry Rules

A retry policy should define:

- Total attempts, whether counting the initial attempt or retries only.
- Which exceptions trigger retries and which go straight to the DLQ.
- Initial backoff, maximum backoff, and multiplier.
- Jitter so multiple consumers do not retry in lockstep.
- Overall timeout per event.
- Retry limits relative to time and downstream capacity.
- Behavior when publishing to the DLQ itself fails.

Example exponential backoff:

| Attempt | Illustrative wait time |
|---:|---:|
| 1 | Process immediately |
| 2 | 1 second |
| 3 | 2 seconds |
| 4 | 4 seconds |
| 5 | 8 seconds |
| Afterward | Route to DLQ or retry topic per policy |

These durations are illustrative only. Add jitter and a total time cap to avoid retry storms. Never block a consumer thread for an extended period waiting for a dependency to recover.

### 2.2. In-Place Retries vs. Broker-Backed Retries

**In-place retries** (binder retry or listener retry) are simple, keep messages inside the consumer flow, and suit small attempt counts with short durations. In some configurations, the consumer thread remains blocked during backoff, delaying other messages.

**Broker-backed retries via topic/queue** move failing messages to a waiting destination with TTL/delay. Consumers can keep processing other events while the failing event waits for its next attempt. This requires topology design, attempt-count headers, routing back to the main queue, and loop limits.

Never stack multiple retry layers without a shared retry budget. For instance, 3 binder retries × 3 HTTP client retries × 3 retry-worker rounds can multiply into dozens of downstream calls for one event.

## 3. Event Envelope and Metadata for Recovery

When routing a message to a DLQ, preserve enough context to trace its origin and replay it safely. Never store only the exception message.

Example event envelope:

~~~json
{
  "eventId": "evt-01J8ORDER7K3",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "aggregateId": "order-1042",
  "aggregateSequence": 17,
  "occurredAt": "2026-11-24T09:10:00Z",
  "correlationId": "checkout-883",
  "tenantId": "tenant-a",
  "payload": {
    "orderId": "order-1042",
    "customerId": "customer-91",
    "currency": "VND",
    "total": 1250000
  }
}
~~~

This is the business envelope. Transport and failure metadata should live in message headers or a separate failure envelope:

| Field | Purpose |
|---|---|
| `eventId` | Stable identifier for deduplication |
| `eventType`, `schemaVersion` | Select the right deserializer/handler |
| `aggregateId`, `aggregateSequence` | Restore per-entity ordering |
| `originalDestination` | Original destination |
| `consumerGroup`/subscription | Consumer that processed the message |
| `originalPartition`, `originalOffset`, or message ID | Trace source location |
| `failedAt`, `occurredAt` | Measure message age and lifetime |
| `attemptCount` | Cap retry/replay loops |
| `exceptionType`, `errorCode` | Error classification |
| `exceptionMessage` | Sanitized error description |
| `stackTraceRef` | Reference to logs/traces, avoiding oversized headers |
| `replayBatchId`, `replayedBy` | Audit the replay execution |

Keep the original payload intact. If a payload must be corrected, store the original, the patched version, the approver, the reason, and the schema version. Never write tokens, passwords, payment card details, or full PII into exception headers.

### 3.1. Do Not Equate Event ID with Broker Message ID

A broker message ID, Kafka offset, RabbitMQ delivery tag, or Pulsar message ID is transport metadata. They do not replace the business `eventId`:

- A Kafka offset is meaningful only within a single topic-partition.
- A RabbitMQ delivery tag is bound to a channel and delivery attempt and changes on redelivery.
- A Pulsar message ID identifies a position in a ledger/topic, whereas `eventId` follows the event contract.

During replay, the republished message gets a new broker ID. Preserve the original `eventId` so consumers recognize it represents the same business effect.

## 4. Overall Error-Handling Workflow

~~~mermaid
flowchart TD
    A[Consumer receives event] --> B[Validate and process]
    B -->|Success| C[Commit offset / ACK]
    B -->|Transient error| D{Retry budget left?}
    D -->|Yes| E[Backoff and retry]
    E --> B
    D -->|No| F[Publish/route to DLQ]
    B -->|Permanent error| F
    F --> G{DLQ publish succeeded?}
    G -->|No| H[Keep source un-ACKed / retry recovery]
    H --> F
    G -->|Yes| I[ACK source per binder semantics]
    I --> J[Investigate, fix root cause]
    J --> K{Approved for replay?}
    K -->|No| L[Hold in quarantine/parking lot]
    K -->|Yes| M[Bounded batch replay]
    M --> N{Processing succeeded?}
    N -->|Yes| O[Mark recovered]
    N -->|No| P{Replay budget exhausted?}
    P -->|No| M
    P -->|Yes| L
~~~

Crucially, never acknowledge the source message as completed before routing the failed message to the DLQ is guaranteed under the binder/broker's semantics. If the DLQ publish fails while the source is ACKed, the message is lost. If the DLQ publish succeeds while the source ACK fails, duplicates can appear in the DLQ; recovery consumers must be idempotent.

## 5. Common Retry and DLQ Configuration in Spring Cloud Stream

Spring Cloud Stream provides error-handling hooks at the message handler layer, though specific capabilities depend on the binder and middleware. For imperative `Function<T,R>` or `Consumer<T>`, exceptions thrown by the handler propagate back to the binder to apply retry/error handlers. Without proper recovery configuration, errors may simply be logged and messages dropped. Never assume every binder implements DLQ identically.

Example input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-service
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
~~~

The consumer properties above are common binding configurations. `processOrder-in-0` must match the binding name derived from function `processOrder`. `group` establishes a stable consumer group; the Kafka binder's DLQ requires an explicitly declared group.

### 5.1. Imperative and Reactive Functions Differ

For imperative handlers, Spring Cloud Stream can apply retries at the message handler layer. For reactive functions like `Function<Flux<T>, Flux<R>>`, the function wires a `Publisher` rather than being invoked per message; retry/error handling must be built using Reactor operators inside the pipeline. Do not copy `max-attempts` and assume asynchronous errors inside a `Flux` automatically land in a DLQ. Review reactive error handling and binder-specific semantics.

### 5.2. Do Not Expect Binder DLQ When Registering a Custom `ErrorMessage` Handler

If an application defines a custom `Consumer<ErrorMessage>` for a binding, that custom handler may override the framework/binder error handlers. In that case, the binder's built-in DLQ mechanism stops running automatically. If custom error handling is needed, explicitly route failed messages to the recovery destination and test ACK/publish paths; never enable both mechanisms without understanding their precedence.

## 6. Kafka Binder: Enabling DLQ for a Consumer Group

The Kafka binder does not enable DLQ by default. The consumer must declare an explicit group and set `enable-dlq` on the target binding.

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-service
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
~~~

The full property path above is `spring.cloud.stream.kafka.bindings.processOrder-in-0.consumer.enable-dlq`. Target the exact input binding name; setting it on an output binding or a mismatched binding name will not enable DLQ for the consuming function.

Once retries are exhausted, the record is sent to the DLQ topic. By default, the DLQ name is:

~~~text
error.<destination>.<group>
~~~

For the example above:

~~~text
error.orders.created.order-service
~~~

You can customize the name with `dlq-name` or a `DlqDestinationResolver` bean. Kafka DLQ does not apply to anonymous groups and cannot be used when `destinationIsPattern=true`.

### 6.1. Error Headers and Partitions

The Kafka binder adds headers such as:

- `x-original-topic`
- `x-exception-message`
- `x-exception-stacktrace`

These headers are stored as `byte[]` in the Kafka record. By default, failed records are routed to the same partition number in the DLQ as the source partition. This helps if replays need to preserve relative per-partition ordering.

When customizing DLQ partition counts:

- Without `dlq-partitions`, the binder typically creates a partition count matching the source topic.
- With `dlq-partitions: 1`, all failed records may route to partition 0 unless a `DlqPartitionFunction` is provided.
- With more than 1 partition, provide a `DlqPartitionFunction` to determine target partitions.

Do not create a single-partition DLQ and assume it preserves ordering across all source partitions. If per-key ordering is a business requirement, verify partitioning and replay design explicitly.

### 6.2. Note on `max-attempts`

When DLQ is enabled, binder retries honor `max-attempts`. When DLQ is disabled, current Kafka binder documentation notes that `max-attempts` does not necessarily govern retries as expected; errors may fall back to Spring for Apache Kafka container defaults. Therefore, verify both `enable-dlq` and the container error handler when determining exact retry counts.

## 7. Kafka: Building a Dedicated Replay Worker

Spring Cloud Stream does not decide on its own how DLQ records should be handled. A recovery application must read the DLQ, inspect messages, and decide whether to replay or move them to a parking lot. Two common strategies:

1. Run replay while the main consumer is paused or stopped to avoid immediately burning through retries on ongoing transient errors.
2. Use two stages: DLQ → replay staging topic → original topic. The staging stage allows review, rate limiting, and auditing before messages re-enter the main flow.

### 7.1. Binding Configuration for Replay

Example replay application:

~~~yaml
spring:
  cloud:
    function:
      definition: replayDlq
    stream:
      output-bindings: orders-replay-out-0;orders-parking-out-0
      bindings:
        replayDlq-in-0:
          destination: error.orders.created.order-service
          group: order-dlq-replay
        orders-replay-out-0:
          destination: orders.created
        orders-parking-out-0:
          destination: orders.created.parking-lot
~~~

`order-dlq-replay` is a dedicated group for the recovery worker. Do not reuse `order-service`, as reading the DLQ is a separate processing stream. Using a dedicated group keeps DLQ offsets independent.

### 7.2. Bounded Replay Attempts

The following example illustrates routing between replay and parking lot. In production, verify replay authorization, approved batch membership, fix status, and publish outcome before acknowledging the DLQ source message.

~~~java
@Configuration
class OrderDlqReplayConfiguration {

    private static final String REPLAY_COUNT = "x-replay-count";
    private static final int MAX_REPLAYS = 3;

    @Bean
    Consumer<Message<byte[]>> replayDlq(StreamBridge streamBridge) {
        return failed -> {
            Integer current = failed.getHeaders()
                    .get(REPLAY_COUNT, Integer.class);
            int replayCount = current == null ? 0 : current;

            String output = replayCount < MAX_REPLAYS
                    ? "orders-replay-out-0"
                    : "orders-parking-out-0";

            MessageBuilder<byte[]> builder =
                    MessageBuilder.fromMessage(failed)
                            .setHeader(REPLAY_COUNT, replayCount + 1);

            Object sourcePartition = failed.getHeaders()
                    .get(KafkaHeaders.RECEIVED_PARTITION_ID);
            if (sourcePartition instanceof Integer partition) {
                builder.setHeader(BinderHeaders.PARTITION_OVERRIDE, partition);
            }

            Message<byte[]> recoveryMessage = builder.build();
            boolean accepted = streamBridge.send(output, recoveryMessage);
            if (!accepted) {
                throw new IllegalStateException(
                        "Recovery publish was not accepted: " + output);
            }
        };
    }
}
~~~

Key imports:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.cloud.stream.binder.BinderHeaders;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.kafka.support.KafkaHeaders;
import java.util.function.Consumer;
~~~

This illustrates control flow, not proof that the broker durably persisted the republished message. `StreamBridge.send()` returning `true` shows the output channel accepted the message; it does not prove the target consumer processed it. Production setups must configure appropriate producer confirmations/transactions and only ACK the DLQ record after recovery output is confirmed per binder semantics. If publishing fails, the consumer must throw so the DLQ record remains eligible for redelivery.

The `BinderHeaders.PARTITION_OVERRIDE` header preserves the source partition number in this example. Use it only when the target topic has matching partitions and business ordering requires preserving partitions. If partition counts changed, apply an intentional partition mapping rather than forcing a nonexistent partition number.

### 7.3. Replay Limit Is Separate from Main Consumer Retry Limit

`x-replay-count` is recovery workflow metadata. The main consumer still maintains its own retry budget per delivery. If a replayed event fails again, it can return to the DLQ. The replay worker reads the header again and increments the counter until moving it to the parking lot.

Never rely on an arbitrary header controllable by external producers to permit unlimited replays. The replay worker must validate the DLQ source, batch ID, and server-side policy; headers serve only as tracking data.

## 8. RabbitMQ Binder: DLX and DLQ

The RabbitMQ binder maps destinations to exchanges and queues per consumer group. For named groups, you can instruct the binder to auto-create the dead-letter exchange and dead-letter queue.

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-service
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
              requeue-rejected: false
~~~

Important properties:

- `auto-bind-dlq`: provisions the DLQ and DLX/routing infrastructure for the binding.
- `republish-to-dlq`: makes the binder republish failed messages to the DLQ with exception metadata headers.
- `requeue-rejected`: when retries are disabled or republishing is not used, controls whether rejected messages are requeued back to the source queue.
- `dead-letter-queue-name`, `dead-letter-exchange`, `dead-letter-routing-key`: customize the topology.
- `dlq-ttl`: TTL on the DLQ when used as a delayed-retry tier.

The default DLQ name is typically destination plus `.dlq` (with group/prefix per topology). When `max-attempts > 1`, the binder retries first; once exhausted, the message moves to the DLQ. When `max-attempts=1`, keep `requeue-rejected=false` so messages do not loop back into the queue indefinitely.

### 8.1. Avoiding Infinite Requeue Loops

Setting `requeue-rejected=true` with `republish-to-dlq=false` can cause continuous requeuing and redelivery. This is only suitable when the cause is guaranteed transient and another backoff/limit exists. For data errors or code bugs, the message will monopolize consumers and generate constant load.

Special exceptions like `ImmediateAcknowledgeAmqpException` bypass the DLQ and discard the message. Never throw such exceptions for unreconciled errors if policy requires retaining failed messages.

### 8.2. Confirming DLQ Publication

With the RabbitMQ binder, if the consumer is transacted, DLQ publishing can participate in the transaction in supporting versions. If the connection factory enables publisher confirms/returns, the binder can wait for confirmation and check whether the message was returned. Upon a negative ack or returned message, the binder can fall back to broker-level dead-lettering via rejection.

Verify your RabbitMQ binder version and confirms configuration before relying on these semantics. Never assume `republish-to-dlq=true` guarantees every publish succeeds.

## 9. RabbitMQ: Replaying from DLQ

The Spring Cloud Stream RabbitMQ binder does not provide a single built-in mechanism to consume from a DLQ and return messages to the original queue. You can build a recovery app using `@RabbitListener`, `RabbitTemplate`, or a dedicated consumer binding.

For unpartitioned destinations, a simple example:

~~~java
@Component
class RabbitDlqReplayListener {

    private static final String DLQ = "orders.created.order-service.dlq";
    private static final String ORIGINAL_QUEUE = "orders.created.order-service";
    private static final String PARKING_LOT = "orders.created.order-service.parking";
    private static final int MAX_REPLAYS = 3;

    private final RabbitTemplate rabbitTemplate;

    RabbitDlqReplayListener(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @RabbitListener(queues = DLQ)
    void replay(Message failed) {
        long count = failed.getMessageProperties().getRetryCount();
        if (count < MAX_REPLAYS) {
            failed.getMessageProperties().incrementRetryCount();
            rabbitTemplate.send(ORIGINAL_QUEUE, failed);
        }
        else {
            rabbitTemplate.send(PARKING_LOT, failed);
        }
    }
}
~~~

This illustrates a retry counter and direct queue routing. With complex exchange/routing-key topologies, restore the original exchange and routing key from metadata:

- When `republish-to-dlq=false`, RabbitMQ typically records dead-letter info in the `x-death` header (queue, exchange, routing-keys, reason, count).
- When `republish-to-dlq=true`, the binder attaches original exchange/routing-key headers along with exception metadata.
- For partitioned destinations, multiple partitions may share one DLQ; replay must read partition/routing metadata from headers instead of routing everything to a default partition.

### 9.1. Delayed Replay Using TTL or Delayed Exchange

You can configure a DLQ with a TTL and a dead-letter exchange pointing back to the source queue to build a delayed-retry loop. This suits transient errors that resolve over time, provided an `x-death` or retry counter enforces a stopping point. Without a cap, poison messages cycle between the DLQ and the source queue forever.

RabbitMQ Delayed Message Exchange requires the corresponding broker plugin. When using it, align exchange types and routing keys with your topology. Never confuse delayed delivery with an operator-managed parking lot.

### 9.2. Confirmation During RabbitMQ Replay

The replay worker must not ACK the DLQ message until the message is published to the target queue and confirmed per publisher settings. If the worker crashes after publishing but before ACKing, the DLQ message can be redelivered and republished as a duplicate. Thus, event IDs and consumer idempotency remain necessary even with publisher confirms.

## 10. Pulsar Binder: Retry Topics and Dead-Letter Topics

Spring Cloud Stream provides an Apache Pulsar binder built on Spring for Apache Pulsar, leveraging Pulsar's producer/consumer settings. Exact DLQ/retry behavior depends on the binder version, Spring Boot/Spring Pulsar version, subscription type, and how consumers are constructed.

Example Pulsar consumer configuration at the Spring Boot level:

~~~yaml
spring:
  pulsar:
    consumer:
      retry-enable: true
      dead-letter-policy:
        max-redeliver-count: 5
        dead-letter-topic: persistent://public/default/orders-DLQ
        retry-letter-topic: persistent://public/default/orders-RETRY
        initial-subscription-name: orders-dlq-ops
~~~

These belong to Spring for Apache Pulsar properties. If the application has multiple input bindings, root-level properties may apply to all Boot auto-configured consumers. Use extended binding properties or customizers per your binder version to isolate settings per binding and verify which properties actually reach the consumer.

### 10.1. Subscription Type Affects DLQ Support

With Spring for Apache Pulsar `PulsarListener`, standard `DeadLetterPolicy` DLQ support applies only to `Shared` subscriptions. `Exclusive` and `Failover` are designed around ordering guarantees; redelivery/DLQ can alter order. For other subscription types, Spring for Apache Pulsar provides `PulsarConsumerErrorHandler`/recoverers so applications can manage recovery explicitly.

The Pulsar native client can support DLQ on `Shared` and `Key_Shared` depending on client version. Do not assume all subscription types in the binder share identical semantics. Consult documentation for your exact version and test with partitioned topics.

### 10.2. Negative Acknowledgment and Retry Letter Topics

Pulsar `negativeAcknowledge` asks the broker to redeliver a message. However, negative-acknowledgment redelivery counts are held in memory; when a subscription dispatcher closes, a broker restarts, a topic unloads, or a consumer disconnects, the counter can reset. Thus `maxRedeliverCount` may never be reached if relying solely on negative acknowledgments.

For reliable bounded retries, the Pulsar native client provides `reconsumeLater` with `enableRetry(true)`. Retry counts are stored in message properties on the retry letter topic and survive restarts and rebalances. Once `maxRedeliverCount` is exceeded, the message moves to the dead-letter topic. A retry letter topic differs from arbitrary delayed delivery: it explicitly models failure-driven retry rounds.

### 10.3. Replaying from Pulsar DLQ

A replay worker consumes the dead-letter topic under a separate subscription, validates messages, and republishes them to the original topic or a replay topic. Only ACK the DLQ message after the target publish succeeds with appropriate producer confirmation. Preserve `eventId`, key, schema version, and custom properties; a new broker `MessageId` is assigned upon republishing.

With `Shared` or `Key_Shared`, pay attention to individual acknowledgment and per-key ordering. Cumulative acknowledgment is incompatible with `Shared`/`Key_Shared` when multiple consumers share a subscription. Check subscription policies before replaying.

## 11. Controlled Replay: Operational Policies

Before replaying, answer all of these questions:

1. Has the root cause been fixed or is a safe workaround in place?
2. Which events are selected: the entire DLQ, a time range, a tenant, specific event IDs, or an error code?
3. Does the current consumer support the event's schema/version?
4. Could side effects have already occurred partially before the failure?
5. Will replaying disrupt ordering by aggregate, partition, or key?
6. Is the main consumer running? If so, will replaying immediately exhaust its retry budget?
7. What maximum replay rate can downstream databases and APIs sustain?
8. Who approved, who executes, which batch ID applies, and where are results logged?
9. Which events move to the parking lot if replay fails again?

### 11.1. Replay Only Selected Events

Never replay the entire DLQ blindly by default. Support filtering by:

- `failedAt` time window.
- Specific `eventId` or an approved ID list.
- `errorCode`/`exceptionType`.
- Verified `tenantId`.
- `schemaVersion`.
- Original destination/group.
- Replay batch ID.

Never allow operators to enter arbitrary destinations or topics in commands when the service can map from an allow-listed configuration. Never use untrusted header data to route messages out of scope.

### 11.2. Rate Limiting and Batch Sizing

Fast replays can send huge traffic spikes into consumers and downstream dependencies. Configure:

- Maximum messages per batch.
- Messages per second rate limit.
- Concurrent replay consumer count.
- Pause intervals between batches.
- Circuit-breaker thresholds when error rates or lag climb.
- Permitted execution windows and per-tenant caps.

Example rollout plan:

| Phase | Event count | Rate | Continue criteria |
|---|---:|---:|---|
| Smoke replay | 10 | 1 event/sec | Zero new duplicates or errors |
| Pilot | 100 | 5 events/sec | Error rate and DB latency within SLO |
| Main batch | 1,000 | 20 events/sec | Lag stays below threshold |
| Remainder | As approved | Dynamically tuned | Operator actively monitoring |

These numbers are illustrative only. Actual rates must reflect consumer and downstream system capacity.

### 11.3. Preserving Business Ordering

Kafka preserves ordering within a partition, RabbitMQ depends on queue/consumer/prefetch/ack behavior, and Pulsar depends on subscription type and keys. Replaying can inject an older event behind newer events that were already processed.

For example, `OrderCreated` at sequence 10 goes to the DLQ while `OrderCancelled` at sequence 11 is processed. Replaying sequence 10 afterward can corrupt order state if handlers do not check sequence numbers.

Safeguards:

- Replay ordered by `aggregateId` and `aggregateSequence`.
- Pause or block newer events for the same aggregate when strict ordering is needed.
- Route replays into a staging topic to re-sequence before emitting.
- Enforce version checks / CAS in the database.
- Never blindly rewind old offsets as a default replay mechanism; doing so can replay an entire partition.

### 11.4. Replays Must Be Idempotent

A replay worker may publish successfully and crash before ACKing the DLQ message. The message is redelivered and may be published again. Target consumers must handle duplicates safely.

Deduplication table pattern:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Inside one database transaction:

1. Insert `eventId` guarded by the unique constraint.
2. If it already exists, skip repeating side effects.
3. If new, update business state.
4. Commit both marker and side effect in the same transaction.

Never split `SELECT` followed by `INSERT`, as two consumers can pass the check concurrently. For external APIs, send a stable idempotency key derived from `eventId`; a local DB transaction cannot roll back an HTTP call.

## 12. Parking Lot and Quarantine

A parking lot is the final resting place for events that exhausted retry/replay budgets or cannot recover automatically. Unlike a DLQ, a parking lot must never automatically feed messages back into the source stream.

Move events to the parking lot when:

- The schema cannot be decoded by current code versions.
- The business event is invalid and requires data-owner correction.
- Multiple replay attempts continue failing.
- Permissions or information required for safe execution are missing.
- Partial side effects already occurred and require reconciliation.

A parking lot record should capture the raw payload, event ID and source metadata, attempt/replay counts, final failure reason, trace/log references, the user or service that parked it, timestamp and replay batch ID, and manual resolution status.

Configure dedicated retention and access controls for the parking lot. It may contain sensitive payloads or malformed data; restrict access to authorized operations teams. Never purge it solely to bring backlog counts to zero.

## 13. End-to-End Example: Order Failing Due to Unsupported Currency

Implement the consumer:

~~~java
@SpringBootApplication
public class OrderServiceApplication {

    @Bean
    Consumer<OrderCreated> processOrder(OrderService service) {
        return service::process;
    }
}
~~~

Service:

~~~java
@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void process(OrderCreated event) {
        if (!Set.of("VND", "USD", "EUR").contains(event.currency())) {
            throw new UnsupportedCurrencyException(event.currency());
        }
        repository.createIfAbsent(
                event.eventId(),
                event.orderId(),
                event.currency(),
                event.total());
    }
}
~~~

Suppose the producer emits `currency=XYZ`. The consumer retries per policy, then the Kafka binder routes the record to `error.orders.created.order-service`. Operations inspects the event and confirms it was bad producer data. The producer is fixed to emit valid currencies; the older events are selected by `eventId` and approved for replay.

### 13.1. Pre-Replay Checklist

- [ ] Confirm the producer fix is deployed.
- [ ] Verify the consumer version supports the event schema.
- [ ] Verify the event did not already create the order earlier.
- [ ] Verify event IDs and tenant scope.
- [ ] Identify partitions/keys to preserve.
- [ ] Select the batch ID and event subset.
- [ ] Configure replay rate limit and max replay count.
- [ ] Verify the parking lot destination.
- [ ] Record the approver and operator.

### 13.2. Post-Replay Verification

- [ ] Republished event count equals approved events minus those moved to the parking lot.
- [ ] Consumer processes successfully and deduplication prevents duplicate side effects.
- [ ] Kafka lag / queue depth / backlog returns to normal.
- [ ] DLQ stops receiving the same events from unresolved errors.
- [ ] Unrecoverable events sit in the parking lot with recorded reasons and owners.
- [ ] Replay report archives batch ID, timestamps, success/failure counts, and event lists.

## 14. Testing DLQ and Replay

Unit tests on the service only verify business exceptions; real-broker integration tests are required to verify DLQ routing, retries, ACKs, and replays.

### 14.1. Core Test Scenarios

| Scenario | Expected outcome |
|---|---|
| Handler succeeds | Message does not enter DLQ |
| Transient error, dependency recovers before retries exhaust | Succeeds after retry |
| Permanent error | Moves to DLQ per policy |
| DLQ publish fails | Source is not ACKed in a way that loses the message |
| Replay publish succeeds | DLQ source is acknowledged per chosen semantics |
| Replay publish fails | DLQ message remains eligible for redelivery |
| Same event replayed twice | Target consumer does not repeat side effects |
| Replay exceeds limit | Message routes to parking lot |
| Replay partition/key | Ordering/partition preserved as required |
| Older DLQ schema | Recovery parses/transforms or quarantines safely |

### 14.2. Kafka Integration Test

With Kafka Testcontainers or a test cluster:

1. Create topic `orders.created` and an explicit consumer group.
2. Enable `enable-dlq`.
3. Send a valid event and verify output.
4. Send an event that throws an exception and observe retry counts.
5. Verify the record appears in `error.orders.created.order-service`.
6. Inspect `x-original-topic`, exception headers, and partition.
7. Run the replay worker on a selected event.
8. Verify the message returns to the original topic and the consumer reprocesses it.
9. Fail an event beyond the replay cap and verify it lands in the parking lot.
10. Kill the replay worker between publish and source ACK to verify duplicates/idempotency.

### 14.3. RabbitMQ Integration Test

With RabbitMQ Testcontainers:

1. Declare exchange, queue, and group.
2. Enable `auto-bind-dlq`.
3. Verify DLX, DLQ, and routing keys are provisioned.
4. Trigger handler failures and verify messages reach the DLQ after retries.
5. Inspect `x-death` or original exchange/routing headers.
6. Replay a message back to the source queue.
7. Verify retry cap and parking lot routing.
8. Simulate publisher nack/return when sending to DLQ/replay to ensure source messages are not lost.

### 14.4. Pulsar Integration Test

With Pulsar Testcontainers or a test cluster:

1. Create topic and suitable subscription type.
2. Enable dead-letter policy with an explicit DLQ topic.
3. Send failing messages and verify retries/redelivery.
4. Verify the DLQ receives messages after max redeliveries.
5. Test broker restarts/consumer reconnects to verify retry count persistence.
6. Replay from the DLQ using a separate subscription.
7. Confirm target publication before ACKing the source.
8. Verify key/ordering with `Shared`/`Key_Shared`.

### 14.5. Test Binder Does Not Replace Broker Integration Tests

The Spring Cloud Stream Test Binder is well-suited for testing functions, bindings, and in-app message flows. It does not replace testing broker-specific features such as Kafka partitions/offsets, RabbitMQ DLX/confirms, or Pulsar retry-letter topics/subscription types. Use the Test Binder for fast logic checks and Testcontainers/cluster tests for broker semantics.

## 15. Observability and Operations

A DLQ workflow requires dashboards and alerts:

| Signal | Purpose |
|---|---|
| DLQ depth by destination/group | Detect accumulating failed messages |
| New events entering DLQ per minute | Spot regressions right after releases |
| Age of oldest message | Detect neglected DLQs |
| Error type/code | Group failures by root cause |
| Average/max retry attempts | Detect retry storms |
| Replay success/failure rates | Measure recovery effectiveness |
| Parking lot depth | Track backlog needing human action |
| Duplicate/dedup count | Detect repeated side effects |
| Replay throughput and downstream latency | Protect target systems |

Never use event ID or customer ID as Prometheus labels due to unbounded cardinality. Keep specific identifiers inside controlled structured logs and traces.

### 15.1. Replay Audit Logs

Every replay execution must log:

- `replayBatchId`.
- Approver/operator or service identity.
- Filter criteria and expected event count.
- Source and target destinations.
- Event IDs or reference list.
- Counts sent, succeeded, failed, and parked.
- Execution rate and time window.
- Consumer version in use.
- Final outcome and dashboard/runbook links.

Never write sensitive payloads or credentials into audit logs. Support halting an in-flight batch and resuming from a clear checkpoint.

## 16. Runbook: Rising Messages in the DLQ

### Step 1 — Scope the Incident

- Identify broker, topic/queue, and group/subscription.
- Determine when the DLQ began growing.
- Check recent releases/deployments around that time.
- Measure DLQ depth, ingress rate, and message age.

### Step 2 — Classify the Errors

- Read error codes/exception types and referenced logs/traces.
- Separate data, schema, business, credential, dependency, and code bug errors.
- Determine whether many events share one failure or a single poison event is involved.
- Check whether side effects partially executed before the handler failed.

### Step 3 — Fix the Root Cause

- Restore dependencies or credentials.
- Patch consumer, serializer, or schema.
- Repair data via an audited process.
- Deploy a tested release.
- Verify a sample failing event succeeds in a test environment.

### Step 4 — Prepare the Replay

- Select event IDs or a batch using approved filters.
- Verify idempotency and ordering constraints.
- Pause the main consumer if the strategy requires it.
- Configure rate limit, max attempts, and parking lot.
- Verify broker-specific producer confirms/transactions/ACKs.

### Step 5 — Execute Replay in Waves

- Run a small smoke batch.
- Inspect results and downstream health.
- Ramp speed gradually within SLO limits.
- Halt immediately if error rates, lag, latency, or duplicates cross thresholds.
- Route persistently failing events to the parking lot.

### Step 6 — Close the Incident

- Confirm DLQ backlog is cleared or assigned to an owner.
- Reconcile business data.
- Archive the audit report.
- Clean up or retire the replay job per retention.
- Update runbooks and alerts if gaps were uncovered.

## 17. Common Mistakes

1. **Omitting DLQ config while assuming retries hold messages forever:** errors may just be logged and dropped depending on the binder/error handler. Always verify recovery policy.
2. **Using an anonymous Kafka group:** the Kafka binder does not support DLQ for anonymous consumer groups. Declare a stable group.
3. **Infinite retries:** poison messages block consumers and grow backlogs. Configure max attempts and a parking lot.
4. **Continuous RabbitMQ requeuing:** `requeue-rejected=true` can trigger endless redelivery loops. Use only for transient issues with backoff/limits.
5. **Assuming all binders share the same properties:** Kafka `enable-dlq`, RabbitMQ `auto-bind-dlq`, and Pulsar `DeadLetterPolicy` carry different semantics.
6. **Replaying the entire DLQ at full speed:** creates traffic bursts and repeats failures. Use filters, batching, and rate limits.
7. **Replaying while the main consumer runs without accounting for retry budgets:** transient issues can burn through retries rapidly. Pause or use two-stage replay.
8. **Dropping original event IDs:** replayed duplicates repeat side effects. Preserve event IDs and idempotency keys.
9. **ACKing the source before target publish is confirmed:** messages are lost if publishing fails. Coordinate confirms/transactions/acks.
10. **Assuming publishing once means processing once:** target consumers can still receive duplicates. Design for at-least-once delivery and idempotency.
11. **Discarding partitions/keys:** replays can scramble ordering or alter routing. Preserve metadata per policy.
12. **No replay count limit:** permanently broken messages loop endlessly. Enforce max replays and a parking lot.
13. **Editing payloads directly in the DLQ:** loses originals and audit history. Keep raw events alongside patched payloads and reasons.
14. **Relying on stack-trace headers as the sole record:** headers can be truncated or absent on the broker. Retain log/trace references.
15. **Treating Pulsar negative-ack counts as durable:** counts reset when dispatchers close. Use retry letter topics when durable retry limits are required.
16. **Using Pulsar DLQ with unsupported subscription types:** verify `Shared`/`Key_Shared` support and binder/client versions.
17. **Purging the DLQ just to silence alerts:** deletes data needed for reconciliation. Delete only after explicit approval and auditing.
18. **Never testing DLQ publish failures:** source messages may be ACKed prematurely. Test broker outages and negative confirms.

## 18. Exercise Completion Checklist

- [ ] Consumer function is bound to the expected destination and group.
- [ ] Retry policy defines limits, backoff, and error classification.
- [ ] DLQ is explicitly enabled for the active binder.
- [ ] Failed events land in the expected DLQ after retries exhaust.
- [ ] Source metadata, event ID, schema, and error details are preserved.
- [ ] Replay worker uses its own dedicated group/subscription.
- [ ] Only selected/approved events are replayed.
- [ ] Replay enforces rate limits, max attempts, and a parking lot.
- [ ] Target publish is confirmed before ACKing the DLQ source per broker semantics.
- [ ] Target consumer is idempotent and preserves required ordering.
- [ ] Dashboards, alerts, and batch auditing are in place.
- [ ] Real-broker integration tests cover duplicates and failure injection.

## Conclusion

A DLQ isolates failed messages for investigation and recovery, while replay is a controlled operational workflow. Spring Cloud Stream offers extension points and binder-specific DLQ configuration, yet Kafka, RabbitMQ, and Pulsar differ in error routing, acknowledgments, retries, and metadata. No single generic property replaces understanding the underlying broker.

A safe recovery pipeline preserves event IDs and source metadata, caps retries, never acknowledges source messages before DLQ/replay delivery is guaranteed, and handles duplicates via idempotency. Replay only after fixing root causes, selecting and approving events, and bounding rate, partitions, and ordering. Unrecoverable events must stop in a parking lot with clear auditing and ownership. Testing publish failures, consumer crashes, and replay duplicates is essential before promoting the workflow to production.

## References

- [Spring Cloud Stream 5.1 — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream 5.1 — Kafka Dead-Letter Topic Processing](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — RabbitMQ Binder Usage and Properties](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/README.html)
- [Spring Cloud Stream — RabbitMQ Dead-Letter Queue Processing](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_dlq.html)
- [Spring Cloud Stream 5.1 — Apache Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring for Apache Pulsar — Message Consumption and Error Handling](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
- [Spring Boot — Pulsar Consumer Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Apache Pulsar — Messaging, Redelivery and Dead Letter Topics](https://pulsar.apache.org/docs/5.0.x/concepts-messaging/)

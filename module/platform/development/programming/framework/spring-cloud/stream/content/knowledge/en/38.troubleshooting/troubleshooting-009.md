# Infinite Retries, Empty DLQ, or Replay Loops

In Spring Cloud Stream, a failing message can be **retried in the application**, **redelivered by the broker**, **routed to a dead-letter queue/topic (DLQ/DLT)**, or **replayed from the DLQ back into the main flow**. Three symptoms—the same message processing endlessly, the DLQ remaining empty despite error-filled logs, and replay sending messages in circles—typically have different root causes. Merely raising `maxAttempts`, restarting consumers, or deleting messages can destroy evidence, trigger retry storms, and corrupt business data.

This lesson belongs to the **Troubleshooting** chapter of the `SPRING_CLOUD_STREAM` module: event-driven applications written with `Supplier`/`Function`/`Consumer` bound to Kafka, RabbitMQ, or Pulsar. It focuses on tracing **which layer owns retry/ack**, conditions required for the DLQ to actually receive data, bounding replays, distinguishing Kafka Binder from Kafka Streams Binder mechanisms, and verifying fixes with realistic fault tests.

> **First Rule:** Never delete topics/queues, reset offsets, purge DLQs, or run bulk replays before recording message IDs, consumer groups/subscriptions, partitions/offsets, retry policies, and database side effects already written. Those actions can lose data or duplicate transactions. Always test in staging and maintain a rollback plan for production.

## 1. End-to-End Diagram of a Failing Message

```text
                Main Destination
                   (topic/queue)
                        |
                        v
               Binder / Consumer
                        |
                        v
                Function handler
                        |
             +----------+-----------+
             |                      |
          Success                 Failure
             |                      |
         Ack/commit                 v
                             Retry in place?
                               /       \
                           Yes           No/exhausted
                           |                 |
                       Backoff               v
                           |            Error/recovery policy
                           +-- reprocess      /       |       \
                                        Requeue     DLQ     Fail/stop/drop
                                          |          |
                                          v          v
                                     Main flow   Replay worker
                                          ^          |
                                          +----------+
```

Not every binder passes through the exact same boxes in this diagram. Kafka uses offsets and a listener container, RabbitMQ uses ack/nack/requeue and DLXs, and Pulsar uses subscription acks/negative acks/ack timeouts/retry-letter topics. A reactive application may retry inside Reactor instead of using binder retries. Determine **actual behavior**, rather than looking only at a property named `maxAttempts`.

## 2. Distinguish Retry, Redelivery, DLQ, and Replay

| Mechanism | Initiator | Sign in Logs / Metrics | What to Watch For |
|---|---|---|---|
| Handler/binder retry | Framework or app code | Same message retried multiple times within one receipt | Bounded attempts, backoff, timeouts, and side effects |
| Broker redelivery | Broker/container/consumer client | Same message ID/offset reappears after nack, disconnect, or restart | App retry counter may reset on redelivery |
| DLQ/DLT | Binder, error handler, or broker DLX | Failing message sent to a dedicated destination | May not be enabled by default; may lack permissions or routing |
| Retry topic / delay queue | App- or broker-designed retry infra | Message leaves main flow briefly and returns after a delay | Distinguish retry topics from the final DLQ |
| Manual / automated replay | Operations or dedicated worker | Messages from DLQ/parking lot republished | Easily loops infinitely if root cause is unfixed |
| Parking lot | Long-term quarantine topic/queue | Events do not keep returning to the main flow | Needs triage workflow, TTL/retention, and audit trail |

**Retry count is not always a system-wide counter.** For example, the app attempts three times, nacks to the broker, the broker redelivers, and the app tries three more times; operators see hundreds of attempts even though each cycle was configured for three. If a DLQ replay back to the source triggers another three-attempt cycle, total attempts grow without bound.

## 3. Recognizing Infinite Retries from Symptoms

Common signs:

- The same `eventId`/payload/partition-offset or broker message ID keeps appearing in error logs.
- CPU climbs and calls to databases/external APIs surge, while **successful** throughput does not increase.
- RabbitMQ `redelivered`/nack/requeue rates spike; queue depth hovers around a fixed level or refuses to drain.
- Kafka consumer lag stalls at a single offset as the container repeatedly seeks/retries; alternatively, the consumer commits forward while a separate replay worker keeps looping.
- Pulsar subscription backlog/redeliveries climb; the same message is redelivered after negative acknowledgment or ack timeout.
- DLQ stays empty despite a high error rate; or messages enter the DLQ only to be immediately pushed back to the source by an automatic replay worker.

Identical error logs alone are **not enough** to conclude the exact same message is being retried: many distinct events with similar payloads can fail the same way. Attach stable identifiers to tell them apart.

Diagnostic log example (never log full sensitive payloads):

```text
2026-11-24T10:00:00Z ERROR binding=processOrder-in-0
 destination=orders.events group=order-projection
 eventId=evt-1082 key=order-42 sourcePartition=2 sourceOffset=711
 cause=InvalidOrderStateException attempt=1

2026-11-24T10:00:02Z ERROR ... eventId=evt-1082
 sourcePartition=2 sourceOffset=711 attempt=2

2026-11-24T10:00:10Z ERROR ... eventId=evt-1082
 sourcePartition=2 sourceOffset=711 attempt=1
```

On the third entry, `attempt` resetting to 1 suggests **a new delivery cycle**, rather than a single `RetryTemplate` looping forever. Correlate consumer restarts/rebalances, nack/requeue events, manual replays, and message headers to see which loop brought the message back.

## 4. Fast Triage Procedure Before Changing Configuration

Follow this sequence so you do not mask the root cause:

1. **Identify the failing message:** `eventId`, business key, timestamp, topic/queue, partition/offset, or Pulsar message ID.
2. **Identify the binding:** function bean name, `<function>-in-0`, `destination`, `group`/subscription, and actual binder.
3. **Classify the error:** deserialization/schema, validation, permanent business error, timeout, authentication/authorization, or transient DB/broker error.
4. **Locate where retries happen:** code (`while`, `retryWhen`), binder retry, Kafka listener error handler, Rabbit nack/requeue, Pulsar negative ack, or replay worker.
5. **Determine the post-exhaustion policy:** skip, stop container, nack/requeue, DLQ, or parking lot.
6. **Verify the actual DLQ:** name, broker/vhost/namespace, publish permissions, partitions, DLX/routing, subscriptions/consumers, and retention.
7. **Verify replay:** are source and target genuinely separate? Is there a durable attempt cap and persisted processing state?
8. **Change only one layer at a time**, emit a uniquely tagged poison message to test, and observe its final resting state.

Do not treat `maxAttempts: 1` as a universal silver bullet across binders: it may only disable binder-level retry while container-level or broker-level redelivery keeps running.

## 5. Classify Errors to Pick the Right Recovery Policy

| Error Category | Examples | Priority Handling |
|---|---|---|
| Transient | HTTP 503, DB failover, brief timeout | Bounded retries, exponential backoff, jitter, alerting |
| Permanent data error | Schema-invalid JSON, invalid enum, missing required field | Quarantine/DLQ, fix data or schema, no hot retries |
| Business rule violation | Stale event version, invalid state | Classify duplicate/stale/gap; do not blindly send all to DLQ |
| Configuration error | Wrong credentials, serializer, topic, ACL | Fix configuration; adding Pods or retries will not help |
| Prolonged dependency outage | Database unavailable for minutes | Circuit breaker, pause/throttle consumer, timed backoff, keep messages safe |
| Deployment mismatch | Incompatible schema contract change | Rollback/canary or fix converter, then controlled replay |

For permanent errors, every retry only burns CPU, network, and log volume; for transient errors, sending straight to the DLQ after one try creates unnecessary operational churn. Pick policies based on failure nature and service **recovery time bounds**.

## 6. Diagnostic Function and Binding Example

An imperative consumer lets the binder observe thrown exceptions:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String eventId, String orderId, String status) {}

@Configuration(proxyBeanMethods = false)
class OrderStreamConfiguration {

    @Bean
    Consumer<OrderEvent> processOrder(OrderService orderService) {
        return orderService::apply;
    }
}
```

`OrderService` is application-provided, and `apply` must throw an exception when mandatory processing fails. For a single function, the binding is named `processOrder-in-0`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-projection
          content-type: application/json
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
            backOffMaxInterval: 10000
```

These are **common retry properties** on the binding. They do not create a DLQ automatically, nor do they prove the Kafka listener container, RabbitMQ broker, or Pulsar consumer stopped redelivering. Actual attempts also depend on binder type, imperative vs reactive model, custom error handlers, and container configuration.

## 7. Distinguish "Handler Throws" from "Handler Swallows"

Pattern that keeps the DLQ empty despite heavy error logs:

```java
@Bean
Consumer<OrderEvent> unsafeConsumer(OrderService service) {
    return event -> {
        try {
            service.apply(event);
        }
        catch (RuntimeException ex) {
            log.error("Failed eventId={}", event.eventId(), ex);
            // Not rethrown -> binder may treat message as succeeded.
        }
    };
}
```

The function **returned normally**, so retry/DLQ mechanisms waiting for an exception may never trigger. If code catches exceptions itself, make an explicit choice: durably quarantine before treating the message as handled, or rethrow for the framework to handle.

Pattern so the binder sees failures:

```java
@Bean
Consumer<OrderEvent> propagatingConsumer(OrderService service) {
    return event -> {
        // On failure, the exception propagates outward.
        service.apply(event);
    };
}
```

Do not immediately swap `catch` for `throw` in production without verifying the binder recovery policy: you could turn a previously skipped error into an infinite retry loop. Verify the DLQ destination and finite retry policy first.

## 8. Reactive Functions Have Different Retry Semantics

For functions of the form `Function<Flux<T>, Flux<R>>`, Spring Cloud Stream does not treat each item as an imperative message handler wrapped by the common retry template/DLQ above. Reactor operators (`retry`, `retryWhen`, `onErrorResume`, `onErrorContinue`) and how the binder integrates reactive pipelines govern behavior.

Pattern that easily triggers unbounded retries:

```java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> riskyPipeline() {
    return input -> input
        .map(this::enrich)
        .retry(); // Can resubscribe infinitely while errors persist.
}
```

A bounded configuration (this is a Reactor example and **does not automatically trigger a broker DLQ**):

```java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> boundedPipeline() {
    return input -> input
        .map(this::enrich)
        .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
            .maxBackoff(Duration.ofSeconds(10)));
}
```

Here `enrich`, `Flux`, and `Retry` must be defined/imported from Reactor in the application. `retryWhen` can resubscribe the entire upstream sequence rather than retrying only a single failed record; it risks re-emitting elements that already produced side effects. When per-message bounded retry is required, design it at the message boundary with idempotency rather than blindly applying a stream-wide retry operator.

## 9. Decision Tree for Endless Retries

```text
Same message ID / offset repeating?
  |
  +-- No: multiple distinct messages failing similarly
  |        -> check schema, input quality, consumer capacity
  |
  +-- Yes:
       |
       +-- Same delivery? attempt increments continuously
       |      -> code retry, binder retry, or listener error handler
       |
       +-- Across deliveries? attempt resets to 1 / rebalance
       |      -> broker requeue, nack/redelivery, offset seek, crash
       |
       +-- Main source finished retrying yet message reappears?
              -> replay worker, TTL retry queue/DLX, or retry topic
```

Log a stable identifier across attempts. If `eventId` cannot be embedded in the payload, log Kafka topic/partition/offset, Rabbit message ID (if producer-supplied), or Pulsar message ID alongside origin metadata. Because the message ID of a **republished** copy can change, preserve `originalEventId`/`originalDestination` to trace across DLQ and replay hops.

## 10. Kafka Binder: DLQ Is Disabled by Default

With the Kafka message-channel binder, DLQ must be enabled explicitly. Key requirements:

1. The input binding has an **explicit consumer group**.
2. Extended consumer property `enableDlq` is enabled on the **exact binding name**.
3. Retries/error handling flow through the mechanism managed by the Kafka Binder DLQ.
4. The DLT topic has compatible partitions/routing and the app has write permissions.

Example:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-projection
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 500
            backOffMultiplier: 2.0
            backOffMaxInterval: 3000
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.events.dlt
```

When input processing fails and binder-managed retries are exhausted, the record is sent to `orders.events.dlt` as configured. Do **not** place `enableDlq` under `spring.cloud.stream.bindings...consumer` because it is a **Kafka Binder extended property**. If using `spring.cloud.stream.function.bindings` aliases, the name in the extended binder branch must match the post-mapping binding name.

By default, the DLQ is typically named `error.<destination>.<group>` when `dlqName` is omitted; setting an explicit name prevents looking at the wrong topic. Do not assume Kafka auto-creates topics under broker policy: verify provisioning and permissions directly.

## 11. Kafka Binder: `maxAttempts: 1` Does Not Always Stop Retries

In modern Spring Cloud Stream Kafka Binder releases, when **DLQ is disabled**, generic binder retry settings do not necessarily control listener container retries. Kafka Binder 5.x documentation notes that by default it falls back to Spring Kafka container retries (such as 10 retries under documented defaults). Thus setting:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            maxAttempts: 1
```

may **not** disable container-level retries. To change policy, check the actual error handler on the listener container and your Spring Cloud Stream/Spring Kafka release. For example, docs show using `ListenerContainerCustomizer` to install a `DefaultErrorHandler` with `FixedBackOff(0L, 0L)` for non-DLQ paths; that is **how to configure container retries**, not a default DLQ setup.

Another container may be customized by the application with unbounded backoff, or code may call `seek` manually so the same offset is re-read. Inspect `ListenerContainerCustomizer`, `ListenerContainerWithDlqAndRetryCustomizer`, `CommonErrorHandler`, `DefaultErrorHandler` beans, and any code calling `Acknowledgment`/seek. Avoid blanket container customizations when only one binding needs a different policy.

## 12. Kafka: DLQ Is Empty Because Failure Happens Before the Handler

Not every failure reaches `Consumer<OrderEvent>` in the business layer. For example, native deserialization errors happen before the message converter builds an object:

```text
Broker record bytes
       |
KafkaDeserializer / native serde
       |        \-- failure before handler runs
       v
Spring Cloud Stream conversion
       |
       v
Consumer<OrderEvent>
```

If an error occurs inside the **Kafka Deserializer** before the framework builds a normal record, the application handler is never called and handler-level retry/DLQ may miss it. The Kafka client may keep failing on the same offset; depending on configuration, the container cannot recover the record to publish to the DLQ. Verify whether the binder uses message conversion or native encoding and whether `ErrorHandlingDeserializer`/an appropriate error handler is configured for that release.

Tests must include schema-corrupt byte payloads, not only `service.apply()` throwing `RuntimeException`. Never reset offsets to "skip over" failures without preserving the bad record or obtaining explicit business approval.

## 13. Kafka: Partitions, Serializers, Permissions, and the DLT Producer

When the Kafka Binder sends a record to a dead-letter topic, many versions preserve the **original partition** when selecting the DLT partition. Consequently, the DLT needs enough partitions or a custom DLQ partition function; if the DLT has fewer partitions, publishing can fail.

For instance, if the source has 8 partitions and the DLT has only 1 partition, do not assume the broker will remap it automatically to a valid partition. You can configure `dlqPartitions: 1` where supported by the binder or a `DlqPartitionFunction` routing records to partition 0; exact syntax and conditions depend on your release.

Also verify:

- Does the DLT topic exist or get auto-provisioned properly?
- Does the broker principal have `WRITE` permission on the DLT?
- Does the DLT producer use serializers compatible with the original payload and error headers?
- Is a `DlqDestinationResolver` routing to a topic other than `dlqName`?
- Is the DLT on a separate Kafka cluster, and is the binder's producer configured for it?
- If using `destinationIsPattern`, does your binder version support DLQ with pattern destinations?

A failure publishing to the DLT can cause the container to keep retrying or stop, leaving the DLT empty. Inspect **DLQ publisher errors**, not just the initial business exception.

## 14. Kafka Streams Binder Differs from the Kafka Message-Channel Binder

**Kafka Streams Binder** runs `KStream`/`KTable`/state-store topologies; do not blindly apply the Kafka message-channel binder's `spring.cloud.stream.kafka.bindings...consumer.enableDlq` to all topology errors. For **deserialization** errors, the Kafka Streams Binder has its own property:

```yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            deserializationExceptionHandler: sendToDlq
```

Depending on version support, you can also pick `logAndFail` or `logAndContinue`. Some releases support configuring handlers on lower-level input bindings. Setting `sendToDlq` here applies to the **deserialization error path**; it does not mean every exception inside processors, joins, aggregations, or output serializers goes to the DLT.

For Kafka Streams **processing/production** errors, check the exception handlers supported by your Kafka Streams version, thread replacement/restart policies, and Streams builder/container customizers. If a topology halts after an error, an empty DLT may be expected when no corresponding handler exists. DLT records from Kafka Streams also have their own partition/destination rules; verify DLT partition counts and configure `DlqPartitionFunction` if needed.

## 15. RabbitMQ: Requeue Can Create an Infinite Loop

RabbitMQ uses `ack` for processed messages and `nack`/reject for failures. Rejecting with `requeue=true` puts the message back on the queue for redelivery. When the root cause is permanently invalid data, this cycle never stops on its own:

```text
Queue -> Consumer
  ^         |
  |         v
  |     Handler fails
  |         |
  +-- nack(requeue=true)
```

In the RabbitMQ Binder, the extended property `requeueRejected` governs whether rejected deliveries return to the queue under binder/container rules. Combining `requeueRejected: true` without republishing failures to a DLQ can cause **continuous redelivery**. Never try to fix this by adding consumers: more consumers simply re-receive the poison message faster.

To bound failures, configure finite retries at the application/binder layer and **then reject without requeue into a dead-letter exchange**, or use controlled republishing to a DLQ.

## 16. RabbitMQ: Intentional DLQ Configuration

Example with `processOrder-in-0`, destination `orders.events`, and group `order-projection`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-projection
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
            backOffMaxInterval: 5000
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
```

`autoBindDlq` lets the binder declare the DLQ/DLX/routing when provisioning conditions permit. `republishToDlq` tells the binder to republish failures so error metadata headers are attached; `requeueRejected: false` prevents returning failed messages back to the main queue along that reject path. Newer versions may have different historical defaults for `republishToDlq` — declaring it explicitly avoids ambiguity.

If queues/exchanges are pre-provisioned by infrastructure teams, leaving `autoBindDlq` off by default avoids accidentally modifying existing topology. Mismatched queue arguments can raise `PRECONDITION_FAILED`; compare against live broker state and plan migrations before changing DLX arguments.

## 17. RabbitMQ: Why `autoBindDlq` Can Still Show No Messages

Setting `autoBindDlq: true` only declares resources when provisioning succeeds. Messages still may not reach the DLQ if:

1. **The handler swallows errors** and returns normally — the listener acks the message.
2. **Infinite requeue** — messages never enter the dead-letter path.
3. **Wrong queue name:** the binder names queues from destination/group/prefix/partition; operators may be inspecting another topic's `.dlq`.
4. **DLX/routing key mismatch:** messages are dead-lettered, but no queue is bound to receive them, so they vanish from pending queues.
5. **`republishToDlq` fails:** publish is rejected, credentials lack permissions, connection/channel fails, or metadata/headers exceed size limits.
6. **Queue TTL/expiry or max-length:** messages land in the DLQ but expire/drop before observation.
7. **A consumer is reading the DLQ:** `messages_ready=0` because messages were already consumed/acked elsewhere.
8. **Special exceptions bypass the DLQ:** for example, `ImmediateAcknowledgeAmqpException` acknowledges immediately without dead-lettering.
9. **DLQ exists in another vhost or broker:** the application and management UI point to different environments.

On RabbitMQ, inspect both `messages_ready` and `messages_unacknowledged`, consumer count on the DLQ, DLX/routing policies, `x-death` headers, and exception headers if present. `x-death` is not a universal business counter for every **republish** path: republishing creates a fresh publish, which can differ from native broker dead-lettering.

## 18. Native Dead-Lettering Differs from Binder Republish

Two common paths:

```text
A. Broker DLX:
main queue -> reject(requeue=false) -> DLX -> DLQ

B. Binder republish:
main queue -> handler fails -> binder publishes to DLQ
                                -> acks/recovers original message per binder mechanism
```

With native DLX, the broker relies on the dead-letter exchange and routing key; with republish, the application sends a new message carrying error metadata and must ensure the publish succeeds. Persisting to the DLQ and acknowledging the original **can have a failure window** if not protected by appropriate transactions/confirms. `transacted` policies, publisher confirms, and recovery when DLQ publishing fails must be verified via integration tests rather than assuming `republishToDlq=true` provides exactly-once delivery.

If DLQ is enabled yet messages remain in the main queue, verify whether the binder is doing **reject + requeue** or **republish**. Never change both mechanisms at once before knowing which one is actually active.

## 19. RabbitMQ: Avoiding TTL Loops Back to the Main Queue

One delayed-retry pattern uses a retry queue with a TTL and a dead-letter exchange pointing back to the source:

```text
main queue --error--> retry queue
                     TTL 30s
                       |
                       v
                   DLX to main
                       |
                       +--> consumer fails again
                                 |
                                 +--> retry queue ...
```

This loop **can be an intentional design** for delayed retries, but it must have a finite cycle limit. If the retry queue always dead-letters back to main with no counter or parking lot, a poison message loops forever. Setting `x-message-ttl` only **slows** the loop; it does not bound the number of cycles.

RabbitMQ quorum queues offer a **delivery limit** option, and some broker versions include dead-letter cycle detection under certain conditions, yet you should not rely on them as a substitute for an application retry policy. They have their own semantics and do not cover all application-level republish loops.

Better design: after `N` cycles (durably counted via application metadata or an appropriate broker policy), route the message to a **parking-lot queue** that never routes back to main; replay only manually or via an approved job.

## 20. Pulsar: Negative Acknowledgment and Ack Timeout

A Pulsar consumer can redeliver messages via several mechanisms:

- `negativeAcknowledge` when processing fails.
- Acknowledgment timeout (`ackTimeout`) when received but not acked in time.
- Consumer disconnect/crash causing the broker to redeliver unacknowledged messages.
- Retry-letter topic with `enableRetry(true)`/`reconsumeLater`, when used by the application.

Critically, **negative acknowledgment does not carry the same retry-limit guarantees** as a retry-letter topic. Pulsar documentation warns that negative-ack redelivery counters can live only in memory and reset on broker restarts, topic unloads, dispatcher reconfigurations, or consumer disconnects. Thus `DeadLetterPolicy.maxRedeliverCount` may **never be reached** in some scenarios; the DLQ stays empty even though the message is redelivered dozens of times.

When durable retry counts across restarts are required, Pulsar recommends **`enableRetry(true)` and `reconsumeLater`** to persist retry counts in message properties on the retry topic. Note that this is a Pulsar client feature; how it is exposed via Spring Cloud Stream Pulsar Binder depends on your Spring Pulsar/binder version and must be verified explicitly.

## 21. Pulsar: Illustrating Retry-Letter Topic and Dead-Letter Policy

Example using the **plain Pulsar Java client**, not code automatically enabled by the Spring Cloud Stream Binder:

```java
Consumer<byte[]> consumer = pulsarClient.newConsumer(Schema.BYTES)
    .topic("persistent://acme/orders/orders.events")
    .subscriptionName("order-projection")
    .subscriptionType(SubscriptionType.Shared)
    .enableRetry(true)
    .deadLetterPolicy(DeadLetterPolicy.builder()
        .maxRedeliverCount(5)
        .retryLetterTopic("persistent://acme/orders/orders.retry")
        .deadLetterTopic("persistent://acme/orders/orders.dlq")
        .build())
    .subscribe();

Message<byte[]> message = consumer.receive();
try {
    orderProcessor.process(message.getData());
    consumer.acknowledge(message);
}
catch (RuntimeException exception) {
    consumer.reconsumeLater(message, 30, TimeUnit.SECONDS);
}
```

In this example, `pulsarClient` and `orderProcessor` are application-initialized, and catching `RuntimeException` is illustrative only. Calling `reconsumeLater` produces a retry message that can fail due to producer/ACL/network issues, so production code must handle retry-path failures and test recovery. Never call both `negativeAcknowledge` and `reconsumeLater` for the same failure assuming only one retry copy exists. Supported `DeadLetterPolicy` APIs and subscription types depend on the Pulsar client version.

**Do not copy plain client examples into a Spring Cloud Stream function without understanding the binder's ack/error handling.** If the binder auto-acks after the function returns, manually calling `reconsumeLater` can desynchronize the two mechanisms. When using the binder, verify consumer builder customization, exception handling, and subscription types in your Spring for Apache Pulsar version.

## 22. Pulsar: Why Is the DLQ Empty While Backlog Grows?

Causes to check:

| Category | Example | Verification Method |
|---|---|---|
| No dead-letter policy | Only `negativeAcknowledge` used, no DLT configured | Inspect consumer builder / binder config |
| Wrong subscription type | `Exclusive` used while expecting `Shared` retry/DLQ semantics | Check subscription metadata and version docs |
| Retry-letter topic unused | `enableRetry` disabled, nack counter resets | Check retry topic / `RECONSUMETIMES` property |
| Wrong topic/subscription | Inspecting a DLQ named for a different subscription | Verify full topic name and namespace |
| Retry count fails to accumulate | Consumer reconnect/unload resets in-memory counter | Track redeliveries across restarts |
| Premature ack | Function returns normally before work finishes | Verify ack/commit timing and side effects |
| Missing DLQ producer ACL | Client cannot create/publish to DLT | Check permission logs and producer errors |
| Auto-creation blocked | DLQ/retry topic does not exist | Provision topics and subscriptions per policy |
| Another consumer drains DLQ | DLQ subscription backlog is low even though messages arrived | Check stats across all subscriptions/producers |

Focus on **subscription backlog**, not only aggregate topic stats. One topic can have multiple subscriptions with very different backlogs; looking at the wrong subscription leads to wrong conclusions. Pulsar retry topics and DLTs are ordinary topics with their own retention, permissions, partitions, and namespace policies.

## 23. Summary of Empty-DLQ Clues Across All Three Binders

| Observed Clue | Kafka Binder | RabbitMQ Binder | Pulsar |
|---|---|---|---|
| Handler throws no exception | Record may be treated as succeeded | Container may ack | Subscription may ack |
| DLQ config not enabled | `enableDlq` defaults to false | `autoBindDlq`/DLX must be checked | Needs dead-letter policy / proper retry path |
| Missing/wrong group or subscription | DLQ requires an explicit group | Queue name depends on group/destination | Subscription name governs backlog/DLT |
| Continuous retries | Container seek/recoverer | Nack/requeue | Negative ack, ack timeout, or retry topic |
| Error before business handler | Kafka deserializer/converter | Converter/adapter/broker delivery | Schema decode / consumer receive path |
| Destination failure | DLT name/partitions/producer | DLX/routing/vhost/queue | Full topic name/namespace/subscription |
| Missing permissions | DLT producer `WRITE` | Publish to DLX/DLQ | Admin/topic producer ACLs |
| DLQ has data yet looks empty | Another consumer commits DLT | DLQ consumer actively acking | Another subscription already acked |

Match verification steps to each binder. Never equate `Kafka lag=0`, `Rabbit queue depth=0`, and `Pulsar backlog=0` as identical proofs: each metric measures a different state.

## 24. Replay Loops: The Third Common Culprit

Suppose the main consumer hits a schema error on an event and sends it to the DLQ after three tries. A replay worker continuously reads the DLQ and republishes back to the source with no attempt cap:

```text
orders.events
    |
    v
Consumer fails permanently
    |
    +--> orders.events.dlq
                |
                v
         Replay worker (automatic)
                |
                +--> orders.events
                          |
                          +--> Consumer fails identically ...
```

Each cycle can create a **brand-new record** in the broker with a new offset or message ID, making broker identities look like distinct events. Track `originalEventId`, `originalDestination`, `replayAttempt`, and parent-child publish lineage. If replay code resets or strips the attempt-counter header, retry caps lose all effect.

Loops are not unique to Kafka. RabbitMQ can loop via DLQ TTL + DLX back to main; a Pulsar retry-letter topic or external workflow can republish to the main topic indefinitely. Always inspect **the entire return path** of a message, not only the consumer's retry policy.

## 25. Sound Replay Policy: Processing Must Have a Termination Point

A safe replay architecture uses a **parking lot** and **operator or automated governance decisions**:

```text
main topic/queue
     |
     v
main consumer --(fails after N attempts)--> DLQ
                                         |
                                         v
                                Triage + error classification
                                         |
                         +---------------+--------------+
                         |                              |
                    Fixable                       Unfixable
                         |                              |
                         v                              v
                  Bounded replay                   Parking lot
                         |
                         v
                Back to main (when eligible)
                         |
                   fails again?
                     /   \
                   Yes    No
                   |       |
          increment durable end + audit
            replayAttempt
                   |
             >= limit? -> Parking lot
```

Conditions required before replaying:

1. Root cause of the prior failure is identified with evidence that the failure is **recoverable**.
2. A maximum replay limit is enforced per **original event**, not merely per republished message.
3. Rate limits/throttling and bounded concurrency protect downstream services from cascading failures.
4. Idempotency by `eventId` and version/ordering checks are in place where required.
5. A separate parking lot destination exists that never auto-routes back to main.
6. Audit records capture who/when/why replayed and which schema/code version handled it.
7. DLQ records are marked handled only after forwarding or parking-lot persistence is **durably committed** per policy.

**Never make "replay immediately whenever a DLQ has messages" your default rule.** A DLQ is a holding area for analysis and risk control, not a second hot retry queue.

## 26. Replay Counters Must Survive Republishing and Restarts

A plain header can be stripped by serializers, message converters, proxies, or intermediate hops. Therefore, for critical business flows, persist replay counts **durably** keyed by `originalEventId` in a governance database/ledger or a schema-controlled envelope; reading headers is only an observability optimization.

Example envelope:

```json
{
  "originalEventId": "evt-1082",
  "originalDestination": "orders.events",
  "aggregateId": "order-42",
  "aggregateVersion": 7,
  "replayId": "replay-20261124-001",
  "replayAttempt": 2,
  "firstFailedAt": "2026-11-24T10:00:00Z",
  "lastFailureCode": "VALIDATION_ERROR",
  "payload": {
    "eventId": "evt-1082",
    "orderId": "order-42",
    "status": "PAID"
  }
}
```

`originalEventId` **never changes** across cycles. `replayId` identifies a replay worker action, while `replayAttempt` increments under a single policy. Never blindly trust a `replayAttempt` number supplied by an untrusted publisher; if used to enforce limits, the server must validate and durably record state.

Do not use RabbitMQ `x-death`, Kafka offsets, or Pulsar message IDs alone as global replay keys because they can change on republish. You need a stable business/event identity across queues and topics.

## 27. Replay Decision Logic (Pseudocode)

A governance model can follow this structure:

```text
for each DLQ record:
    originalId = extractOriginalEventId(record)

    lock ledger[originalId] transactionally
    if ledger.state == COMPLETED:
        mark DLQ record as handled, skip duplicate

    if failureReason is permanent and not repaired:
        ledger.state = PARKED
        retain record in parking lot with audit
    else if ledger.replayAttempts >= MAX_REPLAY_ATTEMPTS:
        ledger.state = PARKED
        retain record in parking lot with audit
    else:
        ledger.replayAttempts += 1
        ledger.state = REPLAY_REQUESTED
        persist outbox message to main destination
        commit ledger + outbox transaction

    separate outbox publisher sends with delivery confirmation
    on confirmed publish, mark outbox delivered
    mark DLQ input handled according to the durable workflow
```

This pseudocode intentionally separates the **database transaction** from **broker publishing** so it does not falsely claim `StreamBridge.send()` creates an exactly-once transaction spanning the database and Kafka/RabbitMQ/Pulsar. In real implementations, use transactional outbox, idempotent publishing, or compatible transaction mechanisms to survive crashes between steps. Acking the DLQ before committing the ledger/outbox can drop replay work; acking after publish but before committing the ledger can create duplicates. Test both failure windows.

In systems not requiring strict transactions, at-least-once replay can be acceptable **provided** idempotency and audit controls are present; make that an explicit design choice rather than assuming an exactly-once guarantee.

## 28. Why an `x-retries` Header Alone Is Insufficient

Example header check in a replay worker:

```java
int attempts = message.getHeaders().getOrDefault("x-retries", 0) instanceof Integer n
    ? n : 0;

if (attempts >= 3) {
    // Write to parking lot; do not send back to main.
}
else {
    // Increment attempts and send back to main.
}
```

This snippet illustrates the idea only. It is **insufficient** for production because:

- Kafka/AMQP/Pulsar encode headers differently; numeric headers may read back as `byte[]` or `String`.
- A conversion/republish step may drop headers not permitted by mappers.
- If code rebuilds a message from payload and forgets to copy headers, the counter resets to 0.
- Parallel replay jobs can read the same event and both decide to publish.
- In-memory state is lost across restarts.

Treat header counters as **supplementary signals**, while enforcing final limits in a durable ledger or unique constraint. Simple headers are fine in learning exercises to trace flow, but never treat them as sufficient protection for financial or critical business events.

## 29. Replaying Can Break Per-Key Ordering

Suppose `OrderPaid(v11)` fails and lands in the DLQ while `OrderShipped(v12)` continues through the main flow. An hour later, an operator replays v11. If code blindly overwrites status with whichever event arrived last, state can regress from `SHIPPED` back to `PAID`.

```text
Time      | Event            | Projection
--------- | ---------------- | ----------------
t1        | v10 CREATED      | CREATED
t2        | v11 PAID fails   | CREATED
t3        | v12 SHIPPED      | SHIPPED
t4        | replay v11 PAID  | PAID (wrong if overwritten)
```

Check `aggregateVersion`, `eventId`, state-transition guards, and already-applied state. If events have strict ordering dependencies, **block the key** upon an ordering gap, hold subsequent events in a durable buffer/quarantine, and replay in order. If the business accepts applying the latest event and skipping intermediates, document that contract explicitly and audit the decision.

DLQs do not preserve ordering automatically. Republishing a message to the main topic can even route the new record to a different partition if key serializers or partition counts changed. Keep record/routing keys stable and test the entire pipeline after replay.

## 30. Verify the DLQ Path Before Replaying

Verification steps for a sample event:

1. Create a distinct event ID in staging and make the handler **fail intentionally**.
2. Observe attempt counts and backoff at the application/container level.
3. Confirm the message finally **exits** retries and appears in the exact expected DLT/queue/topic.
4. Verify the DLQ record retains the original payload (or enough data to recover); `originalEventId`, destination, error reason, and timestamp must be inspectable.
5. Pause the replay worker; verify DLQ counts do not automatically drain back to the source.
6. Fix the failure condition or use a succeeding test handler; replay **one** event and verify clean processing.
7. Repeat with a permanent failure to confirm the attempt cap routes the event to the parking lot.
8. Inject crashes before/after publish and ack to prove zero message loss and safe idempotent duplicate handling.

Never start by replaying the entire DLQ before proving a **single message** replay terminates cleanly. In production, enforce rate limits (events/sec) and replay only an approved range of IDs/offsets.

## 31. Safe Kafka Diagnostic Commands

These commands only **read metadata/state** and must target the right cluster:

```bash
# Group + lag + assignment:
kafka-consumer-groups.sh \
  --bootstrap-server kafka-bootstrap:9092 \
  --group order-projection \
  --describe

# Inspect source topic and DLT:
kafka-topics.sh \
  --bootstrap-server kafka-bootstrap:9092 \
  --describe --topic orders.events

kafka-topics.sh \
  --bootstrap-server kafka-bootstrap:9092 \
  --describe --topic orders.events.dlt
```

If the cluster requires SASL/TLS, supply client properties securely and never print credentials into logs or shell history. To inspect DLT records, use a **read-only** consumer in a safe environment with an isolated group; consuming under another group does not delete original Kafka records, though it creates offsets for that diagnostic group. Never use a production group for manual inspection and accidentally shift the replay worker's offset.

**Never run `--reset-offsets --execute`**, delete topics, or alter retention as a first step. Resetting offsets interferes with replay tracking and can cause millions of events to be reprocessed or skipped.

## 32. Safe RabbitMQ Diagnostic Commands

Inspect queues, ready/unacked counts, and consumers:

```bash
rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
```

With multiple vhosts, specify the exact vhost per your CLI syntax. The RabbitMQ Management HTTP API also exposes queue attributes (`arguments` including `x-dead-letter-exchange`, `x-dead-letter-routing-key`) and bindings inside the target vhost.

Checklist:

- Does the queue for `orders.events` + group exist?
- Does the DLQ exist in **the same vhost**?
- Does the main queue have the right dead-letter exchange and routing key?
- Does that exchange have a binding to the DLQ?
- Is a consumer reading and acking the DLQ very quickly?
- Are there TTL, max-length, or quorum delivery-limit settings on the main queue or retry/DLQ?
- Is the binder running `requeueRejected=true` or republishing to the DLT?

**Never run `rabbitmqctl purge_queue`** to stop a retry loop without an approved data-handling decision. Purging destroys queued messages and can impact other consumers.

## 33. Safe Pulsar Diagnostic Commands

Inspect subscriptions and stats using fully qualified topic names:

```bash
pulsar-admin topics subscriptions \
  persistent://acme/orders/orders.events

pulsar-admin topics stats \
  persistent://acme/orders/orders.events

pulsar-admin topics stats \
  persistent://acme/orders/orders.dlq
```

Verify the exact `order-projection` subscription name, backlog/redelivery counts, consumer connections, producers on retry/DLQ topics, and namespace permissions. For partitioned topics, inspect per-partition metadata/statistics using your Pulsar version's commands; do not confuse non-partitioned and partitioned topics.

To confirm durable retry counters, check message properties on the retry topic (`RECONSUMETIMES`, `ORIGIN_MESSAGE_ID`, `REAL_TOPIC`) when using the retry-letter mechanism. With negative acks, broker restarts/unloads can reset in-memory counters, so never treat transient redelivery counts as proof that the retry limit was reached.

Do not reset subscription cursors or skip messages via Admin CLI without a plan to preserve or recover source data. Cursor resets can replay huge slices of a topic or skip messages you need to investigate.

## 34. "DLQ Is Always 0" Can Be a Measurement Illusion

Before concluding the DLQ is broken, check **three independent observation points**:

1. **Did the DLQ producer publish successfully?** Check recoverer logs, broker permissions/producer errors, and publish error metrics.
2. **Does the DLQ destination really exist and hold data on the broker?** Check topic/queue stats in the right vhost/namespace/cluster.
3. **Is a DLQ consumer reading and acking fast enough to keep backlog at 0?** Check producer rate, consumer rate, offsets/cursors, and DLQ processor audit logs.

For instance, a Kafka DLQ topic exists with a rising log end offset, yet the `dlq-replay` consumer group commits equally fast. Zero consumer lag on the replay group does not mean zero records reached the DLQ. Similarly, RabbitMQ `messages_ready=0` can happen because a DLQ processor holds `unacknowledged` messages or already acked them; low Pulsar subscription backlog can mean the cursor advanced while messages still remain under topic retention.

To verify, emit a test record with a known `eventId`, pause the replay consumer if allowed in staging, and observe **producer publish acknowledgments** and broker stats. Never rely solely on backlog depth to diagnose the whole pipeline.

## 35. Custom Error Handlers Can Override Binder Error Handling

Spring Cloud Stream lets you declare a custom `ErrorMessage` handler via `error-handler-definition`. Documentation for modern releases notes that **custom error handlers and binder-provided error handling/DLQs can be mutually exclusive** so the same error is not handled twice. Thus, setting `enableDlq: true` alongside a custom error handler on the binding can leave the DLQ empty.

Configuration to inspect:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-projection
          error-handler-definition: orderErrorHandler
```

Never assume `orderErrorHandler` both logs and triggers the binder's DLQ recoverer. Read the handler's code and the semantics of your Spring Cloud Stream version. If you need both error notifications and DLQ routing, design one unified recovery path (or a non-competing observer) and test the end state rather than enabling two competing handlers.

## 36. Retry Count and DLQ Count: Pick Metrics That Do Not Mislead

| Suggested Metric | Meaning | Usage |
|---|---|---|
| `message_processing_failures_total` | Total processing failures | Break down by exception and binding |
| `retry_attempts_total` | Application-layer retry attempts | Not equivalent to broker redelivery count |
| `broker_redeliveries_total` | Broker redelivery occurrences | Alerts on requeue/nack/ack-timeout loops |
| `dlq_published_total` | Successful DLQ recoverer publishes | Correlate with producer acknowledgments |
| `dlq_publish_failures_total` | Failures writing to DLQ | Early warning for stuck or dropped messages |
| `dlq_backlog` | Messages awaiting processing in DLQ | Combine with rates to spot trends |
| `replay_requested_total` | Replay commands issued | Audit operational intent |
| `replay_succeeded_total` | Replayed events processed cleanly | Do not confuse with publish-called counts |
| `replay_exhausted_total` | Events hitting the replay cap | Must transition to parking lot |
| `parking_lot_backlog` | Quarantined events awaiting triage | Track aging unfixed items |
| `ordering_gap_total` | Messages arriving after missing versions | Spot DLQ/replay ordering impacts |

These metric names are **application naming suggestions**, not a promise that Spring Cloud Stream exposes those exact names out of the box. Use Micrometer/Actuator and real broker metrics with low-cardinality tags (binder, binding, error class, outcome) instead of putting `eventId` into metric labels. Specific IDs belong in controlled logs and traces.

Sensible alerts: **the same event redelivered more than X times in Y minutes**, rising `dlq_publish_failures_total`, or spikes in `replay_exhausted_total`. Alerting solely on DLQ depth misses infinite retry loops where the DLQ stays empty.

## 37. Log at the Right Level Without Making the Incident Worse

During a continuous failure, enabling DEBUG/TRACE across all of Spring Kafka, Rabbit, Pulsar, and the framework can fill disks and tank throughput. Safe approach:

- Filter logs by a specific `eventId`, partition-offset, or subscription message ID.
- Enable verbose loggers **narrowly and briefly** only when needed.
- Log exception class and root cause; reserve full stack traces for sampled occurrences.
- Distinguish `business failure`, `DLQ publish failure`, `consumer disconnect`, `serialization failure`, and `replay publish failure`.
- Never log tokens, SASL passwords, Pulsar JWTs, raw PII, or full sensitive payloads.
- Include application version, binding name, binder type, destination, and group/subscription.

A helpful diagnostic clue: failures repeating on an exact 30-second cadence may point to a retry queue TTL or negative-ack delay, whereas failures milliseconds apart suggest hot requeue or an in-code retry loop. Treat this only as a **clue**, not a substitute for inspecting configuration and broker logs.

## 38. Hands-On Exercise: Three Distinct Failures on the Same Event

Suppose `OrderEvent(eventId="evt-1082", orderId="order-42", status="PAID")` fails with `InvalidOrderStateException`. Prepare test topic/queue `orders.events`, group/subscription `order-projection`, and DLQ `orders.events.dlq` in staging.

**Scenario A — Infinite retry.** Enable broker-specific redelivery looping (e.g., Rabbit requeue) and emit an event with a deterministic error. Observe attempt logs, broker redeliveries, and CPU. Then switch to bounded retry + DLQ and verify the message stops looping and lands in the DLQ after the configured attempts.

**Scenario B — Empty DLQ.** Intentionally catch the exception in the handler without rethrowing. Observe the message treated as successful and the DLQ staying empty. Then propagate the exception, enable the right DLQ binding, and check DLQ topic/queue and producer permissions. On Kafka, also test a payload failing native deserialization to see why the handler is never called.

**Scenario C — Replay loop.** Build a replay worker that automatically sends DLT records back to main in an isolated environment; watch the loop multiply messages. Add `originalEventId`, a durable ledger with `MAX_REPLAY_ATTEMPTS=2`, a parking lot, and fix the underlying error condition. Verify at most two replays happen **per original event** under policy, and that it stays stopped even across worker restarts.

Across all three scenarios, capture before/after counts: handler invocations, broker publish/ack counts, DLQ backlog, database side effects, and events parked in the parking lot.

## 39. Essential Integration Test Matrix

| Test | Setup | Expected Outcome |
|---|---|---|
| Transient failure | Handler fails twice then succeeds | Retries stay within limit; no false DLQ entry |
| Poison message | Handler always throws permanent error | Retries exhaust, loop stops, lands in DLQ/parking lot |
| Swallowed exception | Handler catches and returns | Test proves binder DLQ does not trigger; alert/code fix added |
| Kafka DLQ disabled | `enableDlq=false` | Verifies container recovery behavior instead of assuming DLT |
| Kafka group missing | Group omitted | Do not expect Kafka Binder DLQ to behave as with a group |
| Kafka malformed bytes | Native deserializer throws | Failure handled via dedicated deserialization path |
| Kafka DLT partition mismatch | DLT has fewer partitions than source | Producer error surfaced; no silent data loss |
| Kafka Streams Serde | Input cannot decode | Verifies `sendToDlq` on deserialization-only path |
| Rabbit requeue | Reject + requeue | Observes loop before vs after config fix |
| Rabbit bad DLX routing | DLX lacks a valid binding | DLQ receives nothing; test catches broken topology |
| Rabbit active DLQ consumer | DLQ consumer acks continuously | Backlog stays low even while DLT publisher works |
| Rabbit TTL loop | Retry queue DLXs back to main | Retry cap/parking lot breaks the cycle |
| Pulsar negative ack | Broker/consumer restarts mid-retry | Nack counter may reset; never assume DLT is guaranteed |
| Pulsar retry-letter | `enableRetry(true)`, `reconsumeLater` | Retry count persists in message properties; DLT receives upon exhaustion |
| Replay worker restart | Restart before/after publish | Ledger preserves attempt counts; idempotency stays safe |
| Replay publish failure | Broker rejects publish back to source | DLQ message is not acked as successfully forwarded |
| Stale event replay | Version older than DB projection | Newer state is not overwritten |
| High volume | Burst of poison messages | Rate-limited; no DLQ or replay storm |

In-JVM Test Binder tests function logic and some error routing, but cannot validate Kafka container seeks/rebalances, Rabbit DLX/nack, or Pulsar retry counters. Those require real brokers/Testcontainers or compatible integration environments. Never run destructive fault tests against production data.

## 40. Decision Table: From Symptom to Next Step

| Observed Symptom | Likely Cause | First Check |
|---|---|---|
| `maxAttempts=1` yet Kafka still retries | Listener container still has a retrying error handler | Check `CommonErrorHandler` and binder release docs |
| Kafka retries finish yet DLT stays empty | `enableDlq=false`, missing group, wrong binding, or DLT publish error | Check extended properties, group, destination, permissions |
| Kafka Streams topology dies, DLT empty | Non-Serde exception or handler set to `logAndFail` | Determine whether failure happened in deserialization or processing |
| Rabbit reprocesses same event every second | `requeueRejected=true`, nack/requeue, or TTL loop | Check queue arguments, consumer ack/nack, and DLX |
| Rabbit DLQ declared yet always 0 | Wrong routing/vhost, republish fail, or active DLQ consumer | Check exchange bindings + ready/unacked/consumers |
| Pulsar negative-acks repeatedly, no DLT | Redelivery counter reset or missing policy | Check subscription type, retry letter, and reconnects |
| DLQ spikes then drops rapidly | Automated replay worker or DLQ consumer acking | Pause cleanly in staging; inspect audit/offsets |
| Same business event keeps returning with new offsets | Republished by replay instead of in-place retry | Trace `originalEventId` and replay worker |
| Code fixed yet events still fail | Permanently bad data, unfixed schema, or replayed too early | Inspect root cause on a single sample record |
| Replay reverts DB state to older version | Missing idempotency/version gate | Check ledger/version guards and transactions |
| DLQ publish occasionally fails | ACLs, broker outage, oversized headers, serializer | Check recoverer producer errors and metrics |
| Failing message disappears without reaching DLQ | Handler caught error, early ack, drop, or custom error handler | Trace from receive through ack and recovery |

If the loop source remains unclear, **isolate a single message** in a test environment; use a trace ID and check ack/publish timing at every layer. Never change serializers, retry policies, consumer concurrency, and queue topology all at once, or you will lose track of which change fixed or broke behavior.

## 41. Active Incident Runbook

**In the first 5–10 minutes**, prioritize impact containment over mutating data:

1. Verify the exact broker/cluster and environment; record deployment versions and effective config.
2. Pick one poison `eventId` and trace it from input through retries to DLQ/replay.
3. Check whether queues/topics are growing exponentially; measure error/retry rates vs successful throughput.
4. If a replay worker drives the loop, **pause only the replay worker** per operational runbook and confirm the DLQ/parking lot still retains records.
5. If consumers are overwhelming downstream services, consider reducing concurrency or pausing consumers in the right scope after assessing backlog and SLA impact.
6. Preserve metadata and failure evidence; avoid purges or offset resets.

**During remediation**, identify the root cause, fix binder configuration or bad data, test on one sample record, and roll out via canary. If the issue is permanent schema breakage, raising backoff relieves pressure temporarily but does not replace schema fixes or quarantine. If it is an environmental outage (DB down), pause or apply bounded timed backoff to prevent a retry storm.

**After stabilization**, replay in bounded batches while monitoring successes, failures, and ordering gaps. Never close an incident just because the main queue hit 0 while the DLQ/parking lot remains unaddressed.

## 42. Operating Controlled Replays

A production replay workflow can follow these steps:

1. Create a ticket/approval referencing `source`, `DLQ`, event ID range, volume, and reason.
2. Verify code/schema/ACLs fixed the original root cause.
3. Snapshot DLQ counts beforehand, broken down by error category and event age.
4. Pick a 1–10 event canary, send rate-limited, and verify end-to-end processing.
5. Record a ledger keyed by `originalEventId` so two operators or workers never replay the same event twice.
6. Scale batches gradually within downstream throughput limits; verify database state/versions.
7. For unrecoverable events, move them to the parking lot with a final disposition reason.
8. Close with a report of `requested`, `published`, `consumed_successfully`, `parked`, `duplicate_skipped`, and outstanding counts.

Never delete failure history simply because an event replayed cleanly. Retain minimal audit records per retention/privacy policy; encrypt sensitive payloads or reference by ID instead of spilling them into logs.

## 43. Protecting Ordering, Idempotency, and Delivery

A consumer can receive the same message multiple times under at-least-once delivery. Foundational safeguards:

- Attach a stable `eventId` backed by a unique constraint/deduplication ledger in storage.
- Check `aggregateVersion` or business sequence before applying updates.
- Write the new state and mark the event processed inside the same DB transaction.
- Ack/commit only after mandatory side effects are durably persisted.
- When replaying older events, explicitly decide to skip or repair ordering gaps instead of blindly overwriting.
- Distinguish `message processed` from `message successfully published to DLQ/replay topic`.

Safer at-least-once processing flow:

```text
Receive event
  -> begin DB transaction
  -> if eventId already applied: skip duplicate
  -> else validate version and apply state change
  -> store eventId in processed-events table
  -> commit DB transaction
  -> acknowledge/commit broker message
```

If a crash happens **after DB commit but before broker ack**, the event can be redelivered. Thanks to the unique constraint and version check, the consumer does not duplicate side effects. If publishing to a DLQ/replay topic fails, use another at-least-once workflow or outbox; never claim a single database transaction automatically synchronizes with the broker.

## 44. Checklist Before Declaring the Issue Fixed

- [ ] Identified binder and programming model: imperative, reactive, or Kafka Streams.
- [ ] Identified actual input binding, destination, and group/subscription.
- [ ] Stable event ID links retries, redeliveries, and replays.
- [ ] Pinpointed the exact retry layer: code, binder, container, or broker.
- [ ] Bounded retry caps and backoff match exception classification.
- [ ] For Kafka, checked `enableDlq`, group, and DLT producer/partition errors.
- [ ] For Kafka Streams, separated Serde errors from processing exceptions.
- [ ] For RabbitMQ, checked `requeueRejected`, `autoBindDlq`, DLX/routing/vhost.
- [ ] For Pulsar, accounted for negative ack/ack timeout behavior vs persistent retry-letter counters.
- [ ] Verified failing records genuinely reach the right DLQ, not merely a log saying "sent."
- [ ] Checked whether an active DLQ consumer is draining the backlog back to 0.
- [ ] Replays run only after recoverable root causes are fixed and under durable attempt caps.
- [ ] Parking lot does not auto-route back to the main topic/queue.
- [ ] Idempotency and version/ordering guards protect against stale event replays.
- [ ] Tested crashes across publish, DB commit, and ack/offset commit boundaries.
- [ ] Zero retry/replay storms when sending a poison record in staging.
- [ ] Dashboards/alerts cover replay attempts, DLQ publish failures, and DLQ backlog.
- [ ] Purging and offset resets are never used as default troubleshooting fixes.

## 45. Self-Check Questions

1. How does a retry inside `RetryTemplate` differ from a broker-triggered redelivery after a nack or disconnect?
2. Why is `maxAttempts: 3` insufficient to conclude a RabbitMQ message will be processed at most three times total?
3. On the Kafka Binder, in which configuration namespaces must group and `enableDlq` be declared?
4. Why might `maxAttempts: 1` fail to disable Kafka listener container retries in some newer releases?
5. If a handler catches an exception and returns normally, will the DLQ automatically receive the message?
6. What kind of loop can RabbitMQ `requeueRejected: true` create?
7. What is the difference between a Rabbit broker DLX and the binder's `republishToDlq`?
8. Why might Pulsar negative ack never reach `maxRedeliverCount` across consumer reconnects?
9. When you need durable retry limits in Pulsar, how does a retry-letter topic differ from negative ack?
10. What category of error does `sendToDlq` in the Kafka Streams Binder primarily handle?
11. Why is an `x-retries` header alone not always enough to prevent a replay loop?
12. What must be handled when replaying event version 11 after version 12 has already updated the DB?
13. If DLQ backlog is 0, what three observation points must you check before concluding the DLQ is broken?
14. Why must a parking lot be separated from any automatic return path to the main destination?
15. If a replay publish fails right after committing the DB ledger, what mechanism prevents losing the replay request?

## Conclusion

**Infinite retries**, **empty DLQs**, and **replay loops** can only be solved permanently after clearly separating **function exceptions**, **binder/container retries**, **broker redeliveries**, and **replay workflows**. For Kafka Binder, inspect `enableDlq`, group, DLT producer, partitions, and listener error handlers; for Kafka Streams Binder, note its separate deserialization handling. For RabbitMQ, control requeue/nack, DLX/routing, and republishing; for Pulsar, distinguish negative acks from retry-letter topics with durable counters. In all cases, combine bounded retries, appropriate backoff, explicit DLQs/parking lots, event-ID replay ledgers, idempotency, ordering guards, and fault-injection integration tests. **A DLQ is not a self-healing mechanism, and replay should never run unattended forever.**

## References

- Spring Cloud Stream — General Error Handling: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html
- Spring Cloud Stream — Kafka Binder DLT Processing: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html
- Spring Cloud Stream — Kafka Binder Configuration Options: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html
- Spring Cloud Stream — Kafka Streams Binder Error Handling: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/error-handling.html
- Spring Cloud Stream — RabbitMQ Consumer Properties: https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html
- Spring Cloud Stream — RabbitMQ Binder Overview: https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-overview.html
- Spring Cloud Stream — Pulsar Binder: https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html
- Apache Pulsar — Message Redelivery, Retry Letter Topics and Dead Letter Policies: https://pulsar.apache.org/docs/4.0.x/concepts-messaging/
- Spring Kafka — Handling Exceptions: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- RabbitMQ — Dead Letter Exchanges: https://www.rabbitmq.com/docs/dlx

# commitCallback

In Spring Kafka, `commitCallback` is the callback that receives the outcome of an asynchronous offset commit operation. The callback informs the application whether the commit succeeded or failed, along with the offsets included in that commit. It is a useful extension point for logging, emitting metrics, and investigating commit failures in a consumer group.

`commitCallback` does not decide which records were processed and does not replace listener acknowledgment. The listener container still determines when offsets are eligible to commit based on `AckMode`. The `syncCommits` setting determines whether the container uses synchronous or asynchronous commits. When using asynchronous commits, the callback is invoked once the Kafka client receives the commit request result.

## 1. Three Distinct Steps: Processing, Acknowledgment, and Commit

When a listener processes a record, three events must be distinguished:

1. **Business processing:** the listener performs work on the record, such as updating an order or writing data to a database.
2. **Acknowledgment:** the listener container marks the record or batch as processed according to `AckMode`. In manual modes, the listener calls `Acknowledgment.acknowledge()` to confirm.
3. **Offset commit:** the container sends selected offsets to Kafka to persist consumer group progress.

`commitCallback` belongs to the third step. It reports the outcome of an asynchronous commit request, not that the listener just finished processing a record.

```text
Kafka poll()
    |
    v
Listener processes record
    |
    v
Container records acknowledgment per AckMode
    |
    v
Container selects offsets to commit
    |
    v
commitAsync(offsets, commitCallback)
    |
    v
Kafka returns commit result
    |
    v
commitCallback(offsets, exception)
```

If the listener processes successfully yet the commit request fails, the record may be redelivered after the consumer restarts or partitions move to another member. If the commit succeeds, the consumer group has a new progress checkpoint to resume from. Thus, the callback helps observe progress persistence, while business safety still depends on processing and acknowledgment order.

## 2. What Do Offsets in the Callback Represent?

Kafka offset commits normally store **the next position to read**, not the offset of the last processed record. For example, the listener processes a record at offset `41` successfully and the container commits offset `42`. When the callback receives the offset map, `42` is the checkpoint the consumer group will use to resume reading.

The callback has this signature from the Kafka client:

```java
void onComplete(
    Map<TopicPartition, OffsetAndMetadata> offsets,
    Exception exception
)
```

Meaning of the two parameters:

| Parameter | Meaning |
|---|---|
| `offsets` | Map of partitions and offset metadata sent by the client in the commit request. Key is `TopicPartition`; value is `OffsetAndMetadata`. |
| `exception` | `null` when the commit succeeded; contains the exception if the commit request failed. |

For example, a single commit can cover multiple partitions:

```text
orders-0 -> offset 120
orders-1 -> offset 85
orders-2 -> offset 310
```

Each offset value is independent per partition. Do not sum offsets to form a single topic-wide progress metric. When logging results, include topic, partition, and offset so logs can be correlated with record-processing logs.

## 3. When Does Spring Kafka Invoke commitCallback?

Spring Kafka's `ContainerProperties` provides two related settings:

- `syncCommits`: decides whether the container commits via `commitSync()` or `commitAsync()`; defaults to `true`.
- `commitCallback`: callback passed to asynchronous commit operations; by default Spring Kafka provides `LoggingCommitCallback` to log commit errors.

When `syncCommits` is `false`, the listener container uses asynchronous commits and invokes the callback when the Kafka client receives the result. When `syncCommits` is `true`, the container uses `commitSync()`; the async callback is not invoked for that synchronous commit.

These two options address different concerns:

| Setting | Commit Mechanism | Result Observation Behavior |
|---|---|---|
| `syncCommits=true` | Container waits for `commitSync()` to complete or throw an error. | Result is handled inline in the synchronous commit flow; `commitCallback` is not the hook for this commit. |
| `syncCommits=false` | Container sends `commitAsync()` and continues operating without waiting for the result at the call site. | `commitCallback` receives the offset map and exception when the asynchronous result returns. |

`AckMode` still determines when the container selects offsets to commit. For instance, `AckMode.RECORD` selects progress after each successful record listener call, whereas `AckMode.BATCH` normally commits after processing a poll's batch. Switching `syncCommits` to `false` does not by itself alter these acknowledgment rules; it changes how commits are dispatched and how commit outcomes are received.

## 4. Configuring the Callback in Spring Kafka

You can configure the callback on `ContainerProperties` of the listener container factory. The example below enables asynchronous commits and logs results:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);

    ContainerProperties container = factory.getContainerProperties();
    container.setSyncCommits(false);
    container.setCommitCallback((offsets, exception) -> {
        if (exception != null) {
            log.error("Kafka offset commit failed for {} partitions",
                    offsets.size(), exception);
            return;
        }

        offsets.forEach((topicPartition, offsetMetadata) ->
                log.debug("Kafka offset committed: topic={}, partition={}, nextOffset={}",
                        topicPartition.topic(),
                        topicPartition.partition(),
                        offsetMetadata.offset()));
    });

    return factory;
}
```

Key imports:

```java
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
```

In real applications, `ConsumerFactory` belongs to package `org.springframework.kafka.core`; import this Spring Kafka type accurately. `TopicPartition` and `OffsetAndMetadata` often need no explicit import inside a lambda, though they are useful when implementing the callback as a separate class.

When using multiple listener container factories, configure the callback on the factory that `@KafkaListener` actually uses. You can specify the factory by name:

```java
@KafkaListener(
    topics = "orders",
    containerFactory = "kafkaListenerContainerFactory"
)
public void consume(OrderCreated event) {
    orderService.handle(event);
}
```

For the listener container to manage offsets, the Kafka consumer is typically configured with `enable.auto.commit=false`. In Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      group-id: order-service
```

If the application uses a custom `ConsumerFactory`, check the factory's actual properties because custom configuration can override Spring Boot values.

## 5. Writing the Callback as a Separate Component

When a callback is shared across multiple listener factories or needs standalone unit testing, you can implement `OffsetCommitCallback` as a class:

```java
import java.util.Map;

import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.consumer.OffsetCommitCallback;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderOffsetCommitCallback implements OffsetCommitCallback {

    private static final Logger log =
            LoggerFactory.getLogger(OrderOffsetCommitCallback.class);

    @Override
    public void onComplete(
            Map<TopicPartition, OffsetAndMetadata> offsets,
            Exception exception) {

        if (exception != null) {
            log.error("Offset commit failed: partitions={}",
                    offsets.keySet(), exception);
            return;
        }

        offsets.forEach((partition, metadata) ->
                log.info("Offset commit succeeded: topic={}, partition={}, offset={}",
                        partition.topic(),
                        partition.partition(),
                        metadata.offset()));
    }
}
```

Attach the class to the container factory:

```java
factory.getContainerProperties()
       .setSyncCommits(false);

factory.getContainerProperties()
       .setCommitCallback(new OrderOffsetCommitCallback());
```

A callback is a component for observing and recording results. Do not put business logic such as charging money, updating orders, or sending customer notifications here. If the callback runs again or a commit succeeds while external business logic fails, logic inside the callback cannot easily stay consistent with the original record.

## 6. Handling Successful Commits

When `exception == null`, the Kafka client confirms the commit request succeeded. Applications can use this signal to:

- Write debug or technical audit logs for committed offsets.
- Increment a metric for successful commit counts.
- Record timing or partition count committed if latency is tracked.
- Aid investigations when correlating consumer group progress with processing logs.

Structured log example:

```text
event=offset_commit_result
status=success
group=order-service
topic=orders
partition=2
next_offset=311
```

`group.id` is not a parameter of `OffsetCommitCallback`; if you need to log the group, retrieve it from application configuration or listener container metadata. Do not infer the group ID from thread names or `client.id`, as those carry different meanings.

A successful commit only proves Kafka persisted the offsets sent in the commit request. It does not prove a database committed in the same transaction, an external API finished, or every business effect is durable. Those guarantees must be designed at the record-processing layer.

## 7. Handling Failed Commits

When `exception != null`, the callback reports that the commit request failed. Log the exception alongside partition/offset context for investigation. Common causes include:

- The consumer lost partition ownership due to a rebalance.
- Group membership changed while the commit request was in flight.
- The coordinator or broker was temporarily unavailable.
- Network interruption or request timeout.
- The consumer was shutting down or group generation changed.

Do not log only a generic line like "commit failed" and discard the exception. Exception type, partition details, and timestamp distinguish transient errors from errors caused by the consumer having left the group.

With asynchronous commits, `commitAsync()` does not automatically retry every error like a business retry loop. Kafka preserves callback order matching asynchronous commit calls; manually re-sending an older offset map after a newer commit already occurred can regress progress. Usually, log the error and let the container's subsequent commits update progress. Build custom retry logic only when commit ordering is strictly controlled and group state is understood.

If business requirements demand knowing commit results immediately and handling errors synchronously, consider keeping `syncCommits=true`. `commitSync()` waits for the result and can throw an exception for the container to handle. This can increase processing latency, but makes commit results clearer at the call site.

## 8. Where Does the Callback Run and What Should It Do?

The Kafka client processes asynchronous callbacks on the consumer thread when commit results are received and handled. In a listener container, that is the consumer coordination thread. Therefore, the callback must execute quickly and never block.

Appropriate operations include brief logging, updating thread-safe counters, or emitting lightweight metric signals. Avoid doing the following inside the callback:

- Synchronous HTTP or database calls that could wait for long durations.
- Waiting on `Future.get()` or waiting for another thread to complete.
- Executing heavy business logic or reprocessing entire records.
- Calling the Kafka consumer from an arbitrary thread or sharing the consumer across background threads.

If commit data must be sent to a remote monitoring system, push a small event onto a bounded queue or dedicated executor and let another worker ship it. Keep the callback short, bound the queue, and handle queue-full scenarios so the consumer thread is never stalled.

A callback can be invoked for a commit covering multiple partitions. Iterate over entries in the map and avoid assuming the map always contains only one partition. When only errors are of interest, you can log the exception and affected partition count without emitting one log line per offset.

## 9. commitCallback Is Not an Acknowledgment Callback

A common mistake is treating `commitCallback` as a hook to run code after the listener finishes. Those two moments are not the same.

| Mechanism | Timing | Purpose |
|---|---|---|
| Listener return | Listener method completes normally. | Signals to the container that record processing finished per listener rules. |
| `Acknowledgment.acknowledge()` | Listener calls it in manual modes. | Acknowledges the record or batch to the container. |
| `commitCallback` | Result of an asynchronous commit returned by the Kafka client. | Observes whether the commit succeeded or failed. |

Manual listener example:

```java
@KafkaListener(topics = "orders")
public void consume(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    orderService.handle(event);
    acknowledgment.acknowledge();
}
```

The listener acknowledges after business logic finishes. The container then selects offsets according to `AckMode` and dispatches the commit. The callback runs only if the container uses asynchronous commits. Do not move `acknowledge()` into the callback, because at that stage the callback is reporting commit results—far too late to serve as acknowledgment of initial record processing.

## 10. Impact on At-Least-Once and Duplicate Processing

Suppose the listener processes record offset `90`, updates the database successfully, and then the container sends an asynchronous commit for offset `91`. If the callback reports an error, the committed offset may remain at `90` or an earlier point. When the consumer restarts or the partition moves to another member, record `90` may be re-read.

This is a key reason to design idempotent business logic. For example, the application can use an event ID as a unique key or write an inbox record inside the same transaction as the database update. If the record is redelivered, the application recognizes the event has already been applied and does not trigger the effect a second time.

Conversely, if the application commits offsets before business work finishes, a successful callback cannot rescue lost work if the process stops between the commit and processing. The callback only observes commit outcomes; it does not coordinate Kafka transactions with database transactions.

For Kafka-to-Kafka flows requiring exactly-once semantics, use Kafka transactions with matching producer/consumer settings. For systems writing to external databases outside Kafka, design inbox/outbox or idempotency mechanisms with appropriate transaction coordination; `commitCallback` does not provide exactly-once guarantees for external systems.

## 11. Choosing Sync vs. Async Commits

No single choice fits every consumer. Weigh latency, throughput, and how urgently the call site needs commit outcomes.

| Criterion | Synchronous Commit | Asynchronous Commit + Callback |
|---|---|---|
| Waiting for result | Container waits for `commitSync()` to complete. | Container sends the request and continues; callback receives the result later. |
| Poll loop latency | Can be higher because it waits for broker response. | Typically cuts inline wait time at the commit call. |
| Error visibility | Exception is raised on the synchronous commit path. | Error is delivered to the callback. |
| Retry control | Synchronous exceptions can follow container/application policy. | Must be careful with commit order; avoid retrying stale offsets after newer commits. |
| Best suited for | Need unambiguous commit outcome before proceeding. | Want to avoid waiting on commits every cycle and can observe outcomes asynchronously. |

Before switching to async, measure commit latency and verify whether commits are actually the bottleneck. If the listener is slow due to database or HTTP calls, changing commit mode may not yield meaningful throughput gains. When using async, ensure a callback logs failures and proper dashboards/alerts exist so commit errors are never missed.

## 12. Common Mistakes When Configuring commitCallback

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Callback is never invoked | `syncCommits` is still `true`; container uses synchronous commits. | Verify `ContainerProperties.setSyncCommits(false)` on the exact factory. |
| Callback does not log errors | Custom callback handles only the success branch or omits exception logging. | Check the `exception != null` branch; custom callbacks replace the default callback. |
| Offset logs are hard to correlate | Only logging offset numbers without topic and partition. | Log `topic`, `partition`, and `OffsetAndMetadata.offset()`. |
| Commits fail after rebalance | Consumer no longer holds ownership or group generation changed. | Cross-check revoke/assign logs, group membership, and exceptions. |
| Consumer slows down after adding callback | Callback performs synchronous I/O or waits on long tasks. | Measure callback duration and offload remote shipping to a separate worker. |
| Business logic still duplicates despite another commit succeeding | Record was redelivered before a commit succeeded or business logic lacks idempotency. | Correlate event ID, offset, and processing/commit timestamps; add idempotency. |

A custom callback should always handle both success and failure branches. If you only care about errors, at minimum log the exception together with the offset map details. When replacing the default `LoggingCommitCallback`, do not accidentally lose commit failure visibility.

## 13. Operational Principles

- Understand `commitCallback` as the result callback of an asynchronous offset commit, not a post-listener-invocation callback.
- Keep `enable.auto.commit=false` when the listener container manages acknowledgments and offset commits.
- Choose `AckMode` to define when offsets become eligible to commit; choose `syncCommits` to decide how commits are sent.
- Set `syncCommits=false` when you want `commitAsync()` and want outcomes delivered via callback.
- Handle both `exception == null` and `exception != null` explicitly; log topic, partition, offset, and exception.
- Keep callbacks fast, avoid synchronous DB/HTTP calls, and never block the consumer thread.
- Do not arbitrarily retry an older commit after a newer commit has happened; avoid regressing committed offsets.
- Design business logic to be idempotent because records can be redelivered when commits fail or consumers rebalance.
- Monitor commit counts, commit failures, and commit latency alongside consumer lag to spot anomalies.

`commitCallback` provides visibility into consumer group progress persistence when Spring Kafka uses asynchronous commits. By clearly separating acknowledgment, commit dispatch, and callback outcomes, applications can log failures accurately, investigate rebalances more easily, and keep processing safe when records are redelivered.

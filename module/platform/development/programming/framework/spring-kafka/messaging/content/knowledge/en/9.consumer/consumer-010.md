# Handling Consumers with No Data

In Kafka, a consumer can poll multiple times without receiving any records. This is a normal state when a topic has no new data yet, producers are sending slowly, or the consumer has reached the current end of the log. `poll()` returning an empty `ConsumerRecords` collection does not mean the consumer has terminated, the topic is broken, or the connection has failed. Kafka is a continuous log system; when new records are written to partitions, the consumer can receive them in subsequent polls.

With Spring Kafka, listeners are normally invoked only when the container receives records. When there are no records, the `@KafkaListener` method is not called with an empty list under the default record listener behavior. If an application needs to know when a listener is idle, it should use the container's idle event mechanism or actively monitor metrics. This article explains how to recognize the no-data state, distinguish it from configuration errors, and handle it properly in both `KafkaConsumer` and Spring Kafka.

## 1. An empty poll() is a normal state

A consumer reads data by calling `poll(Duration)`. This call returns available records from the partitions assigned to the consumer. If no records are ready within the wait window, the result can be empty:

```java
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(1000));

if (records.isEmpty()) {
    log.debug("No new records in this poll");
} else {
    for (ConsumerRecord<String, String> record : records) {
        process(record);
    }
}
```

`isEmpty()` checks whether the current poll returned any records. It does not prove the topic is permanently empty, does not indicate the producer has stopped, and does not prove the consumer lost connectivity. A subsequent poll can still receive data just written by a producer.

Kafka does not use a special record to signal that a topic has ended. Topics typically continue receiving data and partitions may expand over time. When a consumer reaches the current end of the log, it is simply waiting for the next record. Therefore, never exit the loop just because a `poll()` call returns empty.

## 2. Distinguishing no records from records with null values

These two states are completely different:

| State | Observed result | Meaning |
|---|---|---|
| No records | `ConsumerRecords.isEmpty()` is `true` | The current poll received no records |
| Tombstone present | `isEmpty()` is `false`, a `ConsumerRecord` has a key and `null` value | Kafka delivered an intentional record, commonly used to mark key deletion in a compacted topic |
| Empty value | Record exists, value is an empty string or empty byte array | Record exists but payload has zero length |

In a compacted topic, a tombstone typically has a key and a `null` value, indicating that the key was deleted from the compacted state. This is still a record with an offset and must be processed according to business rules. Do not use `record.value() == null` to conclude that the consumer has no data.

Example handling tombstones:

```java
for (ConsumerRecord<String, String> record : records) {
    if (record.value() == null) {
        handleDeletedKey(record.key());
    } else {
        processValue(record.key(), record.value());
    }
}
```

If a deserializer rejects data or throws an error, that is a deserialization failure requiring an error handler or `ErrorHandlingDeserializer` in Spring Kafka. A deserialization error is not equivalent to an empty poll.

## 3. How long does a poll wait for data?

The `Duration` parameter of `poll()` is the maximum time the poll call waits for data and handles required consumer activities. For example:

```java
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofSeconds(2));
```

The consumer can return early as soon as data is ready; do not assume every poll always waits the full two seconds. If no records exist yet, the call can complete after a wait window governed by fetch responses and client state. Using a timeout of `0` to poll continuously can create a busy loop, consuming CPU and flooding logs.

Do not confuse the wait time of `poll()` with `max.poll.interval.ms`:

| Property | What does it control? |
|---|---|
| `poll(Duration)` or `pollTimeout` in Spring Kafka | Maximum wait time for a single poll call |
| `max.poll.interval.ms` | Maximum time between two poll calls in a consumer group before the consumer is considered stalled |
| `fetch.max.wait.ms` | Maximum time the broker waits to fulfill a fetch request when data is below `fetch.min.bytes` |
| `fetch.min.bytes` | Minimum amount of data the broker tries to return for a fetch response, if possible |

`fetch.min.bytes` and `fetch.max.wait.ms` work together to balance throughput and latency. If `fetch.min.bytes` is set high, the broker may wait for more data to return a larger response. When insufficient data arrives, the broker still returns once `fetch.max.wait.ms` expires. This configuration can reduce request counts under high load, but increases wait time when traffic is low.

`fetch.max.bytes` caps the maximum data size a broker returns in a single fetch response; `max.partition.fetch.bytes` limits fetched data per partition. These are size caps, not guarantees that the consumer will always receive that many bytes. Large records and broker-side message limits have separate rules so the consumer can still make progress.

## 4. Consumer loop when no data is available

With the raw Kafka client, the straightforward approach is to keep polling, check the result, and process when records arrive:

```java
KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);
consumer.subscribe(List.of("orders"));

try {
    while (running) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1000));

        if (records.isEmpty()) {
            // Can update metrics or log at an appropriate level.
            idlePollCount.increment();
            continue;
        }

        for (ConsumerRecord<String, String> record : records) {
            processAndPersist(record);
        }

        consumer.commitSync();
    }
} finally {
    consumer.close();
}
```

Do not commit solely because a poll was empty. When there are no records, there is no new processing progress to confirm. Periodic commits with no records usually bring no benefit; if an application has a reason to save a specific offset, it must be grounded in processed offsets and consumer semantics.

Do not arbitrarily add a long `Thread.sleep()` after every empty poll. The consumer must keep calling poll to maintain group membership. If you want to reduce check frequency or temporarily pause consumption, consider `pause()`/`resume()` while continuing to poll per Kafka rules. When processing takes significant time, ensure total time between two polls does not exceed `max.poll.interval.ms`.

If the application needs to wait longer to avoid CPU consumption, choose a reasonable poll timeout instead of looping with `poll(Duration.ZERO)`. You can reduce logging on every empty poll and use counters or aggregate metrics to track idle duration.

## 5. Reasons a consumer might receive no records

An empty poll can stem from several causes. Check in order from assignment state to offset position and cluster configuration:

| Cause | Signs and how to verify |
|---|---|
| Producer has not sent new records | Check producer logs, send futures/callbacks, and topic write rate |
| Consumer reached the end of the log | Compare committed/current offset with log end offset per partition |
| Consumer has no assigned partitions | Check `assignment()`, rebalance logs, and topic partition count |
| Wrong topic or wrong cluster | Check `bootstrap.servers`, topic name, active profile, and runtime environment |
| Consumer group already has offset at log end | Check group ID and committed offsets; `latest` can start a new group at the end of the log |
| Records are on other partitions | Check assignments and producer keys/partitions; consumers only read assigned partitions |
| Inappropriate ACLs or permissions | Check client/broker logs and `READ` on topic, `DESCRIBE` on topic, `READ` on group per cluster policy |
| Using `read_committed` | Records belonging to uncommitted or aborted transactions are not returned under this isolation level |
| Topic not yet created or metadata stale | Use Kafka CLI/AdminClient to inspect topic and partitions |

Do not rush to change `auto.offset.reset` when a consumer receives no data. This property only applies when the group has no valid committed offset or the offset falls outside the log range. If the group has a valid offset at the end of the log, even `earliest` will not make the consumer re-read from the beginning.

## 6. Inspecting assignment, offset, and lag

In code, you can inspect assigned partitions after the consumer joins the group:

```java
consumer.poll(Duration.ofMillis(500));
Set<TopicPartition> assigned = consumer.assignment();

if (assigned.isEmpty()) {
    log.info("Consumer has no assigned partitions yet");
} else {
    log.info("Assigned partitions: {}", assigned);
}
```

Assignments may not be ready immediately after `subscribe()`. The first poll helps the client join the group and receive assignments; check after polling and handle rebalance callbacks if needed. Do not conclude a consumer has no data merely by calling `assignment()` right after `subscribe()`.

You can use the Kafka CLI to check consumer group state:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-reader
```

The output shows partition, current offset, log end offset, and lag. If current offset equals log end offset, the consumer may simply be caught up. If lag is large while the listener still receives no records, check assignments, pause state, deserialization errors, isolation level, and client logs. Lag is a point-in-time measurement; it can change continuously as producers keep writing.

Describe the topic to verify partitions and leaders:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

If a topic has multiple partitions and a consumer is assigned only a subset, that can be normal when other consumers in the same group own the remaining partitions. A consumer only receives records from partitions assigned to it.

## 7. Fetch configuration under low or high traffic

Fetch settings can affect how brokers return data:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[fetch.min.bytes]": 1
        "[fetch.max.wait.ms]": 500
        "[fetch.max.bytes]": 52428800
        "[max.partition.fetch.bytes]": 1048576
```

This is an illustrative Kafka client configuration; appropriate values depend on record size, partition count, throughput, and broker limits. Under low traffic or fast-response requirements, a small `fetch.min.bytes` prevents brokers from waiting to accumulate large chunks. Under high traffic, raising the threshold can reduce fetch requests at the expense of potentially longer record wait times. Do not raise fetch limits just to address empty polls if the real cause is the wrong topic, offset, or assignment.

`max.poll.records` is the maximum number of records a single poll returns, not a minimum. Setting a large `max.poll.records` does not create data when the topic has no new records. Setting it too low can reduce throughput; setting it too high can cause batch processing time to exceed `max.poll.interval.ms`.

If a consumer uses `isolation.level=read_committed`, it only reads records from committed transactions. On a partition with an open transaction, the portion of the log past the last stable offset may not be returned yet, even though the broker has received the data. This is expected behavior of transaction-consistent reading, not a poll bug.

## 8. Handling idle state in Spring Kafka

With `@KafkaListener`, the listener method is normally not invoked when the container polls with no records. If the application needs to take action when no data arrives for a period of time, Spring Kafka provides `ListenerContainerIdleEvent`.

You can configure the idle event interval on the listener container:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {
        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setPollTimeout(1000L);
        factory.getContainerProperties().setIdleEventInterval(10_000L);
        return factory;
    }
}
```

In this example, the container polls with a one-second timeout and emits an idle event when no records are received for the configured idle interval. Verify the API and configuration against your project's Spring Kafka version; Spring Boot may also auto-create a listener factory, in which case customize the existing factory instead of creating a duplicate bean with the same name.

Listening for the event:

```java
@Component
public class KafkaIdleMonitor {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleMonitor.class);

    @EventListener
    public void onListenerIdle(ListenerContainerIdleEvent event) {
        log.info("Listener {} idle for {} ms; partitions={}; paused={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions(),
                event.isPaused());
    }
}
```

Assign a clear `id` to `@KafkaListener` to identify the listener in logs and events:

```java
@KafkaListener(id = "ordersListener", topics = "orders")
public void onMessage(String payload) {
    orderService.handle(payload);
}
```

Idle events are useful for recording periods without data, detecting unexpectedly stalled event streams, or triggering application-level health checks. However, idle does not automatically mean the system is broken. A low-traffic topic can remain idle for hours while operating normally.

Events are published from the listener container and may be handled on the consumer thread depending on how the event multicaster is configured. Avoid running long-blocking work inside the event handler because it can stall the poll loop and cause the consumer to exceed `max.poll.interval.ms`. If you need to call an external service or run a long task, offload the work to a bounded executor and monitor its queue; never interact directly with `KafkaConsumer` from another thread.

For listeners running with concurrency, idle events may fire for child containers. Use the listener ID, topic partitions, and paused flag in the event to know accurately which consumer is idle. If the container has paused partitions for backpressure, that state differs from a topic simply having no new data.

## 9. Idle, pause/resume, and backpressure

`pause()` temporarily stops returning records from specified partitions while the consumer continues polling. `resume()` allows the consumer to receive records again. This mechanism is useful when a worker pool or downstream service is overloaded:

```java
Set<TopicPartition> partitions = consumer.assignment();
consumer.pause(partitions);

// Continue calling poll to maintain consumer group liveness.
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(1000));

// When the worker or downstream is ready:
consumer.resume(partitions);
```

This abbreviated example illustrates the API; `pause()`/`resume()` calls must occur on the consumer-owning thread and require tracking paused partitions. `pause()` is not equivalent to `unsubscribe()` or leaving the consumer group. If paused too long without polling, the consumer can still exceed `max.poll.interval.ms`.

Spring Kafka also supports pausing and resuming containers through listener container APIs. When using containers, control them via `KafkaListenerEndpointRegistry` or Spring Kafka-supported mechanisms rather than accessing `KafkaConsumer` directly. Pausing can trigger idle events even when the broker has records; distinguish a paused state from a genuinely empty/no-new-data state.

## 10. Monitoring idle state and alerting

An idle consumer is not necessarily an unhealthy consumer. Alerts should be based on business expectations and normal event cadence. For example, a payment topic expecting events every minute may need an alert after 15 minutes with no records; an end-of-day reporting topic should not use that same threshold.

Monitor a combination of signals:

- Time since the last successfully processed record.
- Listener container idle duration and idle event count.
- Consumer group assignment, current offset, log end offset, and lag.
- Producer send rate and producer-side send errors.
- Number of paused partitions, rebalance state, and deserialization errors.
- Broker health, leader/ISR status, and cluster connectivity.

When building alerts, distinguish at least three cases: no new records because the data source produced no events; consumer has no assigned partitions or is paused; consumer has connectivity, authorization, or deserialization errors. Each case requires a different remediation.

## 11. Diagnostic workflow when a listener receives no messages

1. Confirm the application is connecting to the right cluster and right topic name for the active profile.
2. Use `kafka-topics --describe` to confirm the topic has valid partitions and leaders.
3. Check the consumer group, members, assignments, current offset, and log end offset using `kafka-consumer-groups --describe`.
4. Confirm the listener is not paused and has completed subscribe/rebalance.
5. Check producer send results, record keys/partitions, and the actual topic the producer wrote to.
6. Inspect `auto.offset.reset`, committed offsets, and `isolation.level`; do not reset offsets before understanding the consequences.
7. Read client/broker logs for ACL, metadata, TLS/SASL, deserialization, or transaction errors.
8. If everything is healthy and the topic simply has no events yet, treat empty polls/idle events as a valid state and monitor against business thresholds.

## 12. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Empty `poll()` means the consumer stopped | The consumer is still active and can receive records on the next poll |
| No new records on a topic means Kafka is broken | The topic may simply be idle because producers have not emitted events |
| `auto.offset.reset=earliest` always reads from the start | Only applies when no valid committed offset exists or the offset is out of log range |
| `max.poll.records` is a minimum record count | It is an upper bound on records returned per poll |
| A record with a `null` value means no record | A tombstone is still a record with a key/offset and must be processed per business rules |
| `pollTimeout` is the same as `max.poll.interval.ms` | One is the wait duration per poll, the other is the limit between two poll calls |
| Increasing `fetch.min.bytes` always makes consumers faster | Brokers may wait longer to batch data, increasing latency under low load |
| An idle event means the listener failed | An idle event only reports that the container received no records during the configured interval |

## Checklist

- The consumer loop keeps calling `poll()` when no records are available; it does not exit after an empty poll.
- Never use `poll(Duration.ZERO)` in a busy loop and do not add long sleeps that disrupt group polling.
- Distinguish empty polls from tombstones or records with empty payloads.
- Understand the differences among `pollTimeout`, `max.poll.interval.ms`, `fetch.min.bytes`, and `fetch.max.wait.ms`.
- Verified topic, partition assignment, consumer group, offsets, and producer send results.
- Considered `isolation.level` if producers use Kafka transactions.
- Use `ListenerContainerIdleEvent` when Spring Kafka needs to detect idle state.
- Do not run long-blocking work on the consumer thread or the thread publishing idle events.
- Base idle alerts on the event cadence and business requirements of each topic.

A consumer with no data is a normal state in an event-driven system. What matters is keeping the poll loop running, monitoring assignments and offsets, and distinguishing genuine idle periods from misconfigurations or operational errors. Spring Kafka provides idle events so applications can observe this state without invoking listeners with synthetic dummy messages.

# AckMode TIME

In Spring Kafka, **AckMode.TIME** is an acknowledgment mode managed by the listener container in which the container commits pending offsets once a configured duration has elapsed since the previous commit. This mode allows an application to group multiple processed records into a single time-based commit, rather than committing after every record or waiting for a fixed number of records.

AckMode.TIME controls when consumer group read progress is persisted. It does not alter record contents, partition ordering, or how the listener executes business logic. Because offsets may remain uncommitted for a period after the listener finishes processing, the application must tolerate some records being redelivered if the process stops before the next commit.

## 1. What Is AckMode?

A Kafka consumer can read records and advance its in-memory position before the committed offset is persisted on the broker. The committed offset is the checkpoint the consumer group uses when starting up or recovering after a failure.

The Spring Kafka listener container manages acknowledgment and offset commits via **ContainerProperties.AckMode**. With automatic modes such as RECORD, BATCH, and TIME, the listener does not need to call **Acknowledgment.acknowledge()** itself for each record. The container tracks processing results and decides when to commit according to the configured mode.

**AckMode.TIME** means:

- The listener processes records along the normal flow.
- When the listener processes a record successfully, the container marks the corresponding offset as eligible to commit.
- The container tracks the elapsed time since the previous commit.
- Once **ackTime** has elapsed and there are pending offsets, the container commits the acknowledged offsets.
- After the commit, the timestamp is updated for the next cycle.

**ackTime** is measured in milliseconds in the **ContainerProperties** API. In modern Spring Boot configuration, the **spring.kafka.listener.ack-time** property is bound as a duration, such as **5s**.

## 2. Execution Flow

The diagram below illustrates the concept of TIME mode. The container only commits progress that the listener has processed successfully and that qualifies for acknowledgment under the active error handler.

~~~mermaid
flowchart TD
    A["Consumer poll records"] --> B["Listener container invokes listener"]
    B --> C{"Listener processed successfully?"}
    C -->|Yes| D["Container records processed offset"]
    C -->|No| E["Pass error to error handler"]
    D --> F{"ackTime threshold reached?"}
    F -->|No| G["Continue processing; offset still pending commit"]
    G --> A
    F -->|Yes| H["Commit pending offsets"]
    H --> I["Update last commit timestamp"]
    I --> A
    E --> J["Retry or recover per configuration"]
    J --> A
~~~

For example, suppose the container commits successfully at 10:00:00 and **ackTime** is set to 5 seconds. Records processed successfully at 10:00:01, 10:00:02, and 10:00:04 create pending commit progress. When the container checks the time condition and sees the threshold has passed, it commits the latest offsets for the relevant partitions.

The actual commit time may be later than exactly 5 seconds. **ackTime** is a threshold for the container to decide to commit; committing still depends on the poll loop, listener execution time, batch processing, and broker responsiveness. Do not treat it as a millisecond-accurate real-time deadline.

If there are no new records or no pending offsets, there is no new progress to commit. TIME is not a background job that forces the broker to receive an empty commit every interval.

## 3. Configuring AckMode.TIME

### 3.1 Configuring with Spring Boot

The listener container can be configured via **application.yml**:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      group-id: inventory-service
    listener:
      ack-mode: time
      ack-time: 5s
~~~

In this example:

- **enable-auto-commit: false** prevents the Kafka client from auto-committing on its own schedule. The Spring Kafka container manages commits.
- **ack-mode: time** selects the time-based commit mode.
- **ack-time: 5s** sets the time threshold between commits to 5 seconds.

If an older Spring Boot version binds durations differently, consult the configuration metadata for that exact version. In Spring Kafka's Java API, **setAckTime** takes a value in milliseconds.

### 3.2 Configuring with ConcurrentKafkaListenerContainerFactory

When creating the listener container factory manually, you can set the mode and interval on **ContainerProperties**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);

        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.TIME);

        factory.getContainerProperties().setAckTime(5_000L);

        return factory;
    }
}
~~~

A listener can use this factory:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "inventory-service",
        containerFactory = "orderListenerFactory"
    )
    public void handle(OrderEvent event) {
        inventoryService.reserve(event);
    }
}
~~~

When the listener completes normally, the container records processing progress. The container will commit according to the configured TIME threshold. The listener method does not need an **Acknowledgment** parameter just to use AckMode.TIME.

### 3.3 Verifying the Effective Configuration

In environments with multiple profiles, custom container factories, or programmatic configuration, identify which factory the listener actually uses. Configuration on one factory does not affect listeners using a different factory.

Check at least:

- Which container factory the listener is bound to.
- The effective **AckMode** of the container.
- The effective **ackTime** and time unit.
- The consumer's **enable.auto.commit** setting.
- Whether a transaction manager or error handler alters the commit path.

Do not inspect only a YAML file and conclude the configuration is active. Values can be overridden by profiles, environment variables, or Java configuration.

## 4. How Does AckMode.TIME Differ from Other Modes?

Spring Kafka provides multiple modes to choose how the container acknowledges offsets. The main difference is the condition that triggers the container to commit.

| AckMode | Commit Timing | Characteristics |
|---|---|---|
| **RECORD** | After each record is successfully processed by the listener | Progress is saved frequently; increases commit count |
| **BATCH** | After all records in a poll batch are processed | Groups commits by batch; this is the container's common default mode |
| **TIME** | When time elapsed since the previous commit reaches **ackTime** and pending offsets exist | Groups commits by time |
| **COUNT** | When the number of records processed since the previous commit reaches **ackCount** | Groups commits by count |
| **COUNT_TIME** | When either the time threshold or count threshold is reached | Combines time and record-count bounds |
| **MANUAL** | After the listener calls **acknowledge()**, the container handles commits under manual-mode semantics | Application explicitly acknowledges |
| **MANUAL_IMMEDIATE** | Commits immediately when **acknowledge()** is called on the consumer thread | Application explicitly acknowledges and requests immediate commit |

### TIME vs. BATCH

BATCH commits at the poll boundary: once all records returned by a single poll have been processed. TIME is based on elapsed time since the previous commit, so a single commit can encompass progress accumulated across multiple polls.

If a poll returns a large batch, BATCH can commit as soon as that batch finishes processing, whereas TIME may hold offsets pending until the time threshold is reached. Thus, the two modes behave differently even with the same consumer, listener, and **max.poll.records**.

### TIME vs. COUNT

TIME does not cap the record count with a counting threshold. If throughput is high, very many records can be processed within a single **ackTime** window. COUNT commits when enough records accumulate, regardless of how much time has passed.

### TIME vs. COUNT_TIME

COUNT_TIME is useful when you want both a time threshold and a record-count threshold. The container can commit when either threshold is met. This is worth considering if the application wants to bound both how long offsets are held and how many records are processed without being committed.

### TIME vs. MANUAL

TIME is an automatic container-managed mode. MANUAL requires the listener to actively call **Acknowledgment.acknowledge()**. Do not pick MANUAL just to change commit timing; choose the mode that reflects where the application wants to control acknowledgment.

## 5. Relationship Between ackTime and Committed Offset

An offset is the sequence number of a record within a partition. When committing, the consumer group stores the next position to read—meaning the offset after the last acknowledged record—rather than storing the last record's offset as a processed marker.

For example, suppose a consumer successfully processes records up to offset 104 in partition 0. When committing that progress, the stored committed offset is 105. When the consumer restarts from the committed offset, the next record to read is offset 105.

With AckMode.TIME, the committed offset can lag behind the position the consumer has processed in memory. You can picture three positions:

- **Position**: the position the consumer client has read or advanced to in the current run.
- **Processed position**: the progress the listener has successfully processed.
- **Committed position**: the checkpoint persisted on the broker for the consumer group.

The committed position is the recovery point after a restart. The in-memory position can advance ahead of the committed position while the container waits for the time threshold.

With multiple partitions, a commit carries the respective offset for each partition the consumer owns that has progress to acknowledge. AckMode.TIME does not produce a single global offset for the entire topic.

## 6. Impact on Delivery Semantics

### 6.1 Window Where Redelivery Can Occur

Suppose a consumer processes a record successfully, but the offset has not yet reached the next commit. If the process stops abruptly, the broker only knows the older committed offset. After the consumer restarts or the partition is assigned to another consumer, processed-but-uncommitted records may be redelivered.

Example with **ackTime = 5s**:

| Time | Event | State |
|---|---|---|
| 10:00:00 | Commit succeeds up to offset 100 | Committed offset is 101 |
| 10:00:01 | Offset 101 processed successfully | Not yet committed |
| 10:00:02 | Offset 102 processed successfully | Not yet committed |
| 10:00:04 | Offset 103 processed successfully | Not yet committed |
| 10:00:05 onward | Container checks TIME threshold and commits new progress | Committed offset can advance to 104 |
| Before a successful commit | Process stops | Uncommitted records may be re-read |

The table is an illustrative timeline. Actual commit timing still depends on the container processing loop and actual commit outcome.

TIME does not by itself create exactly-once processing. This mode fits an at-least-once model: records can be redelivered, so business side effects must be safe when executed repeatedly.

### 6.2 Idempotency Is Still Required

If the listener deducts inventory in a database and then the process stops before committing the offset, the record can be redelivered and the listener could deduct inventory a second time. Setting a shorter **ackTime** only narrows the redelivery window in some scenarios; it does not eliminate the race between side effects and commits.

Common safeguards:

- Use a unique **eventId** and record a processed marker in the same database transaction as the business change.
- Place a unique constraint on an inbox table so the same event cannot trigger processing twice.
- Design business operations as upserts or conditional updates that can be re-run safely.
- If the consumer emits downstream events, use a transactional outbox to synchronize database changes and outbound events.

Do not rely on a committed offset as proof that a database or external API completed exactly once.

### 6.3 Commit Time Is Not Processing Time

**ackTime** only controls when the container commits offsets. It does not set a timeout on the listener, does not cancel an in-flight database call, and does not make records process faster.

If a listener processes a record for 20 seconds and **ackTime** is 5 seconds, the container still must wait for the listener to finish within the processing flow before it can acknowledge that progress. A 5-second threshold does not mean that record will be committed exactly 5 seconds after processing begins.

## 7. How to Choose ackTime

The right value depends on redelivery tolerance, commit cost, throughput, and business processing duration.

### Short Intervals

Advantages:

- Read progress is persisted more frequently.
- Fewer records are typically re-read after an abrupt stop under the same load conditions.
- The consumer group has a fresher checkpoint to resume from after a restart.

In return, commits happen more often, which can increase broker requests and commit overhead.

### Long Intervals

Advantages:

- More records can be grouped into a single commit.
- Reduces commit frequency in high-throughput workloads.
- Reduces some overhead associated with offset commits.

In return, more processed records may remain uncheckpointed. When the process stops or partitions rebalance, the consumer may have to reprocess a larger span.

### Practical Selection Approach

Start from business requirements:

1. Identify which side effects need duplicate protection and what idempotency already exists.
2. Determine the acceptable level of redelivery during a process restart or consumer rebalance.
3. Measure current throughput and commit overhead.
4. Pick an intentional initial **ackTime**, such as 1 to 5 seconds for a workload needing relatively frequent checkpoints.
5. Measure commit rate, commit latency, consumer lag, and processing time.
6. Test stopping the consumer abruptly to observe how many records are redelivered.
7. Tune the value based on results, then document it in the runbook.

The 1 to 5 second range is only a starting point for experimentation, not a standard value for every system. A system handling large batches, high throughput, or slow downstreams may need a different choice.

## 8. Related Configuration Factors

### enable.auto.commit

When the Spring Kafka container manages acknowledgments, keep the Kafka client from auto-committing on its own schedule:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
~~~

The Spring Kafka container normally disables auto-commit unless configured otherwise. Setting **false** explicitly keeps intent readable and prevents a profile from accidentally enabling auto-commit. If auto-commit is enabled, the client may persist offsets independently of when the listener completes under AckMode.TIME, breaking checkpoint expectations.

### max.poll.records

**max.poll.records** limits how many records are returned in a single poll. It affects batch size and the time the container needs to process poll results, but it is not TIME's commit threshold.

If a batch has many records and the listener processes slowly, processing may extend past **ackTime**. The container only commits processed progress according to listener and error-handler semantics.

### max.poll.interval.ms

This is the maximum time allowed between poll calls before the consumer is considered stalled and may leave the group. It differs from **ackTime**:

- **ackTime**: the time threshold for the container to decide to commit pending offsets.
- **max.poll.interval.ms**: the time limit between consumer polls.

Increasing **ackTime** will not fix a consumer leaving the group due to taking too long to process a batch. Conversely, increasing **max.poll.interval.ms** does not by itself make offsets commit more frequently.

### pollTimeout

**pollTimeout** controls how long the consumer waits for data during a single poll. It can affect observed latency in the poll loop, but it does not replace **ackTime** and does not set commit timing.

### Synchronous and Asynchronous Commits

The Spring Kafka container can perform synchronous or asynchronous commits based on the **syncCommits** configuration. Commit mode affects whether the container waits for commit results and how commit errors are observed. Inspect actual container configuration and logs when the broker is unresponsive or commits fail.

Regardless of commit mode, do not mark business work as finished simply because the listener ran through. The application must distinguish listener success, commit success, and business side effects.

## 9. Listener Error Handling with AckMode.TIME

AckMode.TIME does not determine the entire exception-handling policy. When a listener throws an exception, Spring Kafka forwards the error to the configured error handler. The error handler can retry, seek to re-read, recover the record, or apply another policy.

Production configuration should answer these questions:

- Which transient errors are retried?
- What are the backoff and retry count?
- When retries are exhausted, by what mechanism is the record recovered or routed to a DLT?
- When the error handler recovers successfully, is the offset committed per **ackAfterHandle** or **commitRecovered** settings?
- If a listener processes a batch and one record fails, which offsets are retained or committed?
- If an offset commit fails after the listener succeeds, how does the application observe and recover?

Do not assume every polled record is automatically committed just because **ackTime** has expired. The container should acknowledge progress only based on processing outcomes and recovery policy. When using a transaction manager, read the transactional listener container semantics because offsets may be coordinated with the transaction instead of being committed independently in the usual way.

### Example Listener with Error Handling

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service"
)
public void handle(OrderEvent event) {
    inventoryService.reserveIdempotently(event.eventId(), event);
}
~~~

In this example, if **reserveIdempotently** throws an exception, the container's error handler decides on retry or recovery. If the listener completes normally, the offset is recorded for TIME-based commit. Business idempotency protects against the case where the record is redelivered before the commit succeeds.

## 10. Observing AckMode.TIME in Production

To verify that TIME mode behaves as expected, observe both commits and record processing.

### Metrics to Monitor

| Metric | What to Observe |
|---|---|
| Consumer lag | Distance between producer and consumer progress |
| Commit rate | Frequency of consumer offset commits |
| Commit latency | Time for broker to respond to commits |
| Records consumed rate | Number of records processed by the consumer over time |
| Listener processing time | Duration to process a record or batch |
| Redelivery / duplicate rate | Frequency of records being reprocessed |
| Rebalance count | Frequency of consumer group membership or assignment changes |
| Retry and DLT rate | Number of listener errors retried or recovered |

Kafka consumer metrics expose metrics related to commits and lag, such as **commit-rate**, **commit-latency-avg**, **commit-latency-max**, and **records-lag-max**. Metric names exported through Micrometer or monitoring systems may be normalized per application conventions.

### Logs Need Sufficient Context

When investigating, log:

- Consumer group and client ID.
- Topic, partition, and offset.
- Listener start/end timestamps.
- Processing outcome and exception if any.
- Commit timestamp and commit outcome if logged.
- Rebalances or partition revocations/reassignments.

Do not log full payloads if they contain sensitive data. Use an event ID or correlation ID to correlate logs between consumers and downstream services.

### Signs of Misconfiguration

- Commit rate too high relative to throughput: review **ackTime**, consumer count, and commit overhead.
- Very low commit rate while records are continuously processed: check **ackTime**, listener container, effective configuration, and commit errors.
- Lag grows despite fast listener processing: check partition distribution, consumer count, fetch settings, and brokers.
- Redeliveries increase after restarts or rebalances: check the gap between processed position and committed position, as well as listener duration.
- Commit latency increases: inspect brokers, network, and group coordinator.

High consumer lag alone does not prove AckMode.TIME is misconfigured. Lag also depends on producer rate, partition count, consumer count, processing duration, and broker capacity.

## 11. Testing TIME Behavior

Test in an environment with a real Kafka broker or equivalent test container. A mocked listener can test business logic but does not prove the container commits offsets at the expected timing.

A useful test should:

1. Create a topic with known partitions and a dedicated consumer group.
2. Configure the listener container with AckMode.TIME and a short **ackTime**, such as 2 seconds.
3. Send several records with distinct event IDs.
4. Wait for the listener to process them successfully and observe the committed offset.
5. Verify that offsets are not necessarily committed immediately after each record.
6. Wait past the time threshold and verify the committed offset advances.
7. Stop the consumer abruptly before a commit in a separate scenario.
8. Restart with the same group ID and verify uncommitted records can be redelivered.
9. Verify idempotency prevents duplicate business side effects.

Do not use a single fixed **Thread.sleep()** as sole proof. Use polling assertions with a timeout to wait until the committed offset or listener state meets the condition. This makes tests less sensitive to machine load and thread scheduling.

### Scenarios to Cover

| Scenario | Expected Outcome |
|---|---|
| Listener processes quickly, before **ackTime** elapses | Offset may still be uncommitted |
| **ackTime** reached and pending offsets exist | Container commits acknowledged progress |
| Process stops before commit | Uncommitted records may be redelivered |
| Process stops after successful commit | Consumer resumes from committed offset |
| Listener throws an exception | Error handler decides retry/recovery |
| Commit fails | Logs/metrics reflect the error; do not assume checkpoint advanced |
| No new records | No new offsets need to be committed |

## 12. Common Configuration Mistakes and Misconceptions

**Thinking TIME commits exactly N milliseconds after each individual record.** **ackTime** is measured from the previous commit, not as a separate timer restarted for each record.

**Enabling auto-commit alongside container-managed acknowledgments.** The client may commit independently of the listener container and violate progress expectations. Check **enable.auto.commit**.

**Using TIME to guarantee zero duplicates.** The process can stop after side effects but before commit. Consumers still need idempotency.

**Using TIME to fix consumer lag.** Committing offsets does not make the listener process faster and does not increase consumer capacity. Inspect throughput, partition assignment, and downstream latency.

**Confusing ackTime with max.poll.interval.ms.** One controls commits; the other limits time between polls. Increasing one does not replace the role of the other.

**Assuming TIME limits the number of uncommitted records.** At high throughput, many records can be processed within the time window. If you need a count-based condition, see COUNT or COUNT_TIME.

**Ignoring error-handler behavior.** Retries and recovery can affect which offsets are considered complete. Verify **ackAfterHandle**, **commitRecovered**, seek, and transaction behavior against the actual configuration.

**Checking only YAML configuration.** Listeners may use another container factory or Java configuration overrides. Verify the running container.

## 13. Runbook for Slow Offset Commits

When offsets do not advance as expected:

1. Identify the consumer group, topic, partition, and current committed offset.
2. Verify the listener is still receiving and processing records.
3. Check the effective AckMode of the listener container.
4. Read the actual **ackTime** value and time unit.
5. Verify **enable.auto.commit=false**.
6. Inspect listener processing time and record count per poll.
7. Check error handler, retries, recovery, and recurring exceptions.
8. Inspect commit logs, commit latency, and broker errors.
9. Cross-check consumer lag and partitions assigned to the consumer.
10. If changing **ackTime**, monitor commit rate, lag, duplicates, and throughput afterward.

If offsets are not advancing because the listener is retrying infinitely or taking too long on one record, lowering **ackTime** will not fix the root cause. Fix the listener or error handler first.

## 14. Pre-Production Checklist for AckMode.TIME

**Configuration**

- [ ] Listener container actually uses **ContainerProperties.AckMode.TIME**.
- [ ] **ackTime** is explicitly set with the correct unit.
- [ ] **enable.auto.commit** is disabled so the container manages commits.
- [ ] Profiles and container factories do not unexpectedly override settings.
- [ ] Sync/async commit and transaction behaviors are clearly understood.

**Business Logic and Recovery**

- [ ] Listener treats processing as successful only after required side effects complete.
- [ ] Consumer is idempotent to withstand redelivery.
- [ ] Error handler has clear retry, backoff, and recovery rules.
- [ ] Procedures exist for handling commit failures and rebalances.
- [ ] DLT/recovery preserves traceability to the original event.

**Observability and Testing**

- [ ] Monitor commit rate, commit latency, consumer lag, and processing time.
- [ ] Test commits after the time threshold elapses.
- [ ] Test stopping the process before and after commits.
- [ ] Test listener exceptions and recovery.
- [ ] Runbook documents how to verify committed offsets and replay.

## 15. Usage Principles

AckMode.TIME is suitable when you want the container to group successfully processed offsets by time interval. The shorter **ackTime** is, the more frequently checkpoints are updated and the more commits may occur. The longer **ackTime** is, the more commit frequency can drop, though the window of unsaved progress can also be larger if the consumer stops abruptly.

Choose the interval based on redelivery requirements and commit overhead, then validate with metrics and failure tests. Keep **enable.auto.commit** disabled, configure error handlers intentionally, and make listeners idempotent. By understanding the difference between processed records and committed offsets, operations teams can predict consumer group recovery behavior and tune AckMode.TIME safely.

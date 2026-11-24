# AckMode COUNT_TIME

In Spring Kafka, **AckMode.COUNT_TIME** is an offset-commit mode managed by the listener container. The container commits pending offsets when either of two conditions occurs: the configured number of records (**ackCount**) has been processed, or the configured duration (**ackTime**) has elapsed since the previous commit. Whichever condition is reached first triggers the next commit.

This mode combines two ways of controlling commit frequency:

- **By count:** during high traffic, the container can commit after each group of records reaches the threshold.
- **By time:** during low traffic, the container still gets a chance to commit on a time cadence without waiting for the full record count.

**COUNT_TIME** is generally suitable when balancing commit overhead against how long offsets remain unpersisted. It reduces commit frequency compared to committing after every record, while avoiding waiting for a large batch of records before committing in low-traffic workloads.

## 1. Offsets and Acknowledgments in Spring Kafka

Kafka stores committed offsets per consumer group and partition. A committed offset represents the next position the consumer group will read when resuming from that checkpoint. For example, if the last processed record had offset 41, the consumer normally commits offset 42.

A successful listener invocation and an offset commit are two distinct events:

1. The Kafka consumer polls records from the broker.
2. Spring Kafka passes the record to the listener.
3. The listener executes business logic and completes successfully.
4. The container records the corresponding offset as eligible to commit.
5. When the AckMode condition is met, the container sends the offset commit request to Kafka.

If the application finishes business work but the process stops before the offset is committed, the group may re-read the record after the consumer starts up or is reassigned the partition. This is the foundation of at-least-once behavior in many consumer configurations.

In Spring Kafka, **AckMode** tells the container when offsets are committed. With container-managed modes, the listener does not need to call **Acknowledgment.acknowledge()** itself for every record. **COUNT_TIME** is an automatic container mode, not a manual mode.

Spring Kafka normally disables Kafka consumer auto-commit when the container manages offsets. Do not arbitrarily enable **enable.auto.commit=true** alongside container commits, as the two mechanisms can make commit timing unpredictable and break assumptions about record processing.

## 2. How Does COUNT_TIME Work?

The two primary thresholds are:

| Property | Meaning |
|---|---|
| **ackCount** | Number of records received and processed since the previous commit to trigger a count-based commit |
| **ackTime** | Duration in milliseconds since the previous commit to trigger a time-based commit |

The container tracks pending offsets and the count/time conditions. When either threshold is reached, the container commits pending offsets per partition.

Example configuration:

- **ackCount = 100**
- **ackTime = 5000** milliseconds (5 seconds)

If the consumer processes 100 records in just 2 seconds, the count threshold is met first and the container can commit once that threshold is processed. If the consumer processes only 30 records in 5 seconds, the time threshold is met first and the container can commit pending offsets after that interval.

~~~text
Thresholds: ackCount = 100, ackTime = 5 seconds

High traffic:
  Previous commit ---- 100 records in 2 seconds ----> Commit
                      ^ count reached first

Low traffic:
  Previous commit ---- 30 records in 5 seconds -----> Commit
                      ^ time reached first
~~~

**COUNT_TIME** represents an OR condition: count reached or time reached. It does not wait for both conditions to be true simultaneously. If you want to commit only when both enough records and enough time have passed, **COUNT_TIME** does not express that policy.

The time condition is not an independent timer guaranteeing commits accurate to the millisecond. The container checks and executes commits while coordinating polling and record processing. Listener processing duration, next poll timing, consumer load, and broker response time can all cause a commit to finish later than the configured threshold.

If no new offsets are pending commit, **ackTime** expiring does not produce a commit with new data. A commit only makes sense when the container has offset progress to persist.

## 3. Scope of Counting and Timing

**ackCount** and **ackTime** apply per consumer container/consumer instance, not as an aggregate counter for the entire application or entire group.

For example, suppose an application has three listener consumers running with concurrency equal to 3. Each consumer has its own processing progress, record count since its last commit, and commit timing. **ackCount=100** should not be understood as waiting for 100 combined records across all three consumers.

When a consumer owns multiple partitions, pending offsets for those partitions are managed within that same consumer. A single commit can include offsets for multiple partitions owned by that consumer. Offsets are still persisted separately per partition within the group.

This means:

- A fast consumer can trigger count-based commits ahead of other consumers.
- A slow or low-volume consumer can trigger time-based commits.
- One consumer committing does not reset another consumer member's counter or timer.
- After a rebalance, the new consumer resumes from the committed offset of each assigned partition.

## 4. Configuring COUNT_TIME in Spring Kafka

AckMode and both thresholds can be set on the **ContainerProperties** of the listener container factory.

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            ordersKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);

        ContainerProperties containerProperties =
                factory.getContainerProperties();
        containerProperties.setAckMode(ContainerProperties.AckMode.COUNT_TIME);
        containerProperties.setAckCount(100);
        containerProperties.setAckTime(5_000);

        return factory;
    }
}
~~~

In this example:

- **setAckMode(COUNT_TIME)** selects the count-or-time commit mode.
- **setAckCount(100)** sets a 100-record threshold.
- **setAckTime(5_000)** sets a 5,000-millisecond time threshold.

A listener using the factory:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

With the listener above, the container records offsets after the listener completes per container rules. When either count or time reaches its threshold, the container commits pending offsets.

When using Spring Boot auto-configuration, AckMode can be selected via listener properties in supported Spring Boot versions:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
    listener:
      ack-mode: count_time
~~~

When precise control over **ackCount** and **ackTime** is needed, configuring **ContainerProperties** directly on the factory expresses both thresholds clearly. Check API and property binding for your Spring Boot/Spring Kafka version; do not assume every version exposes the exact same property set.

### Using application.properties

If configuring only AckMode through Spring Boot:

~~~properties
spring.kafka.consumer.group-id=orders-service
spring.kafka.listener.ack-mode=count_time
~~~

The count/time values can still be set on container properties in Java configuration. You do not need to create an **Acknowledgment** parameter or call **acknowledge()** yourself to use **COUNT_TIME**.

## 5. Comparing COUNT_TIME with Other AckModes

Spring Kafka provides several AckModes to choose commit timing matching how listeners process records.

| AckMode | General Commit Timing | Characteristics |
|---|---|---|
| **RECORD** | After the listener finishes each record | Frequent commits; narrows uncommitted offset window but increases commit cost |
| **BATCH** | After finishing all records of a single poll | Fits batch processing; commits at poll boundary |
| **TIME** | When **ackTime** has elapsed since the previous commit | Time-driven |
| **COUNT** | When record count since the previous commit reaches **ackCount** | Count-driven |
| **COUNT_TIME** | Whichever of **ackTime** or **ackCount** is reached first | Combines time and count thresholds |
| **MANUAL** | Listener acknowledges via **Acknowledgment**; container handles commits per manual rules | Application controls acknowledgment timing |
| **MANUAL_IMMEDIATE** | Commits immediately when listener calls acknowledge depending on thread and settings | Requires clear understanding of threads and commit behavior |

Selection examples:

- Use **RECORD** when you want commits after each record and accept higher overhead.
- Use **BATCH** when processing a full poll batch as one unit of work.
- Use **COUNT** when traffic is steady enough and you want commits after a defined record volume.
- Use **TIME** when you want a time-based commit cadence.
- Use **COUNT_TIME** when workload traffic fluctuates and you want either threshold to trigger commits.
- Use manual modes when business logic must explicitly determine acknowledgment timing.

**COUNT_TIME** does not mean the listener acknowledges records on a timer. It controls when the container commits offsets already recorded after processing.

## 6. COUNT_TIME with Record Listeners and Batch Listeners

With a record listener, the container invokes the listener for each polled record. After the listener finishes, the container records offset progress and evaluates the configured commit condition.

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

With a batch listener, the listener receives a batch of records in a single call. The container must rely on batch processing outcomes to determine which offsets have been processed and can be committed. If a batch listener throws an exception, offset handling and retries depend on the error handler, batch listener semantics, and container configuration.

Batch listener example:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersBatchKafkaListenerContainerFactory")
public void handleBatch(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

With a batch listener, design **processBatch** so that the outcome of each record or the entire batch is handled clearly. If one record in the batch fails after other records have already produced side effects, retrying the batch may re-run side effects for the previously successful records. Use event IDs or idempotency mechanisms to avoid applying business logic twice.

Do not pick **COUNT_TIME** merely because the listener accepts a **List**. Choose AckMode based on the business unit to commit and how the error handler recovers when part of a batch fails.

## 7. What Happens When the Application Crashes Before a Commit?

Suppose **ackCount=100** and the consumer has successfully processed 80 records since the last commit. If the process crashes before reaching 100 records or before **ackTime** expires, the new offsets may not have been committed yet.

When the consumer restarts or partitions are assigned to another member, the consumer resumes from the last committed offset. Some records already processed by the listener before the crash may be re-read.

Example:

~~~text
Committed offset: 100

Consumer processes:
  100 101 102 ... 179
  (80 records produced side effects)

Crash before next commit

New consumer restarts from offset 100
  100 101 102 ... may be reprocessed
~~~

This is at-least-once behavior: records can be reprocessed when side effects completed but offsets were not committed. **COUNT_TIME** does not create exactly-once semantics for databases or APIs outside Kafka.

To withstand re-reads:

- Use a stable event ID for each business event.
- Design database updates to be idempotent.
- Optionally store processed event IDs in the same database transaction as the business change.
- For irreversible external operations, use an idempotency key supported by the target system.
- Monitor offset commits and consumer lag to observe real progress.

Committing offsets before side effects complete risks lost processing: the consumer may not re-read an already-committed record. Therefore, listener containers normally commit after the listener finishes according to the chosen AckMode.

## 8. COUNT_TIME, Retries, and Error Handling

AckMode does not by itself decide how many times a failed record is retried or where it is routed. Handling of failed records depends on the error handler, retry topics, backoff, dead-letter topics, and container configuration.

In Spring Kafka, when a listener throws an exception, the container/error handler decides whether to retry, seek back to an offset, recover the record, or continue. Only offsets considered processed or recovered under policy should be committed.

Several principles:

- Transient errors can be retried with bounded backoff.
- Data errors unrecoverable via retry should be routed to an error-handling flow or DLT per policy.
- Do not commit past a record that has not succeeded if doing so loses the ability to re-read that record.
- Once retries finish and a record is recovered successfully, understand how the error handler affects which offset gets committed.
- Test the combination of AckMode, record/batch listener, and error handler in use.

Example of bounded retry configuration:

~~~java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
                new FixedBackOff(1_000L, 2L));

factory.setCommonErrorHandler(errorHandler);
~~~

This snippet illustrates an error handler retrying with a one-second interval and a bounded retry count per the BackOff configuration. Routing records that exhaust retries to a DLT requires configuring an explicit recoverer if business requirements demand it.

Do not treat **ackCount** as a retry count. **ackCount** counts records to drive offset commits; retry is an error-recovery policy. The two settings serve different purposes.

## 9. Impact of COUNT_TIME on Performance and Reliability

Committing offsets has cost: the consumer sends requests to the broker coordinator and Kafka persists group progress. Committing after every record increases commit requests; committing too infrequently enlarges the unpersisted offset window.

**COUNT_TIME** establishes a balance:

- Under high traffic, the count threshold can trigger commits more often than the time threshold.
- Under low traffic, the time threshold avoids waiting too long to accumulate enough records.
- When the listener is slow, actual commit timing can be later than the threshold because the container must finish processing and polling.
- With multiple consumers, each consumer has its own counter and timer, so commits do not happen synchronously across the whole group.

A small **ackCount** and short **ackTime** produce more frequent commits, reducing the re-readable offset window at higher commit cost. A large count threshold and long time interval reduce commit overhead while increasing how many records may be replayed after a crash.

No single value fits every workload. For order systems, weigh duplicate-processing cost and idempotency. For telemetry, small replays may be acceptable if consumer processing is cheap and data can be deduplicated. For systems updating databases, account for both transaction cost and reprocessing capability.

## 10. Choosing ackCount and ackTime

Choose thresholds based on record rate, processing duration, and how much replay the system can tolerate.

Example of a workload averaging 50 records/second:

- **ackCount=100** corresponds to roughly two seconds at average speed if the consumer processes steadily.
- **ackTime=5000** corresponds to five seconds.
- Under steady conditions, count may be reached before time.
- If traffic drops to 5 records/second, time may be reached before count.

This is only an estimate. Reality depends on poll batches, partition distribution, listener duration, consumer count, and broker commit speed.

A selection process:

1. Determine records per second per consumer, not just total topic throughput.
2. Determine the maximum number of records that can acceptably be re-read after an incident.
3. Estimate commit cost and the group coordinator's capacity.
4. Set **ackCount** to commit in batches under high traffic.
5. Set **ackTime** to bound how long offsets wait for commit under low traffic.
6. Check p95/p99 listener processing duration and poll times.
7. Test under slow brokers, consumer restarts, and rebalances.
8. Tune based on commit latency, lag, and reprocessing rate.

Initial configuration example:

~~~java
containerProperties.setAckMode(ContainerProperties.AckMode.COUNT_TIME);
containerProperties.setAckCount(200);
containerProperties.setAckTime(3_000);
~~~

Values like 200 records or 3 seconds are merely starting examples for measurement. Do not put them straight into production without checking your workload's rate and duplicate-processing consequences.

## 11. Sync and Async Commits

Once the container decides to commit offsets, the Kafka consumer can commit synchronously or asynchronously according to container configuration.

- **Synchronous commit:** the container waits for the commit result. This detects commit errors at the call site, but can block the consumer thread waiting on the broker.
- **Asynchronous commit:** the container sends the commit and continues processing; a callback can report errors later. This reduces waiting on the processing thread, but requires monitoring callbacks and commit ordering.

Spring Kafka exposes **syncCommits** in **ContainerProperties**; the default is typically synchronous commits. A commit callback can be supplied to observe commit results. Specific behavior depends on container version and configuration.

**COUNT_TIME** decides when the container requests a commit. **syncCommits** decides how the container waits for or receives the commit result. These two settings are independent:

| Configuration | Question Answered |
|---|---|
| **AckMode.COUNT_TIME** | When are pending offsets included in a commit? |
| **syncCommits** | How does the container wait for commit results? |
| **ackCount** | How many records since the previous commit trigger a commit? |
| **ackTime** | How much time since the previous commit triggers a commit? |

Do not switch to async commits just to reduce latency without monitoring commit failures. If a commit fails, the group may re-read already-processed records.

## 12. Rebalances and COUNT_TIME

When partitions are revoked, a consumer may still hold offsets pending commit. The container must handle those offsets according to its lifecycle and commit policy. If a consumer loses ownership abruptly, you cannot assume it can still commit successfully.

Example:

1. Consumer A owns partition P0.
2. A processes 70 records, not yet reaching **ackCount=100** and before **ackTime** expires.
3. The group rebalances and P0 is revoked from A.
4. If offsets were not committed, the new consumer can re-read records from the latest commit.
5. Consumer B continues processing P0 under the new assignment.

Do not rely on **COUNT_TIME** to guarantee commits finish before every rebalance. Configure graceful shutdown, revoke callbacks, and side-effect idempotency. Also verify how the container commits pending offsets in your running Spring Kafka version.

## 13. Production Observability

When using **COUNT_TIME**, monitor both record-processing cadence and commit cadence:

- Record consume rate per consumer/member.
- Consumer lag per partition.
- Commit rate and total commit count.
- Average and maximum commit latency.
- Commit failures or exceptions.
- Time elapsed between commits.
- Number of records processed between two commits.
- Listener duration to process a poll batch.
- Rebalance count and number of records re-read after rebalances.

Kafka clients normally expose metrics such as commit rate, commit total, commit latency, and assigned partitions; exact metric names vary by version. Spring Kafka also provides container logs and commit callbacks to aid investigation.

Signals:

| Signal | Investigation Direction |
|---|---|
| Commit rate too high | **ackCount** is small or **ackTime** is short; evaluate overhead vs. replay needs |
| Commit rate too low | Thresholds too large, slow listener, or low-volume consumer; check pending offsets |
| Lag rises despite records being processed | Commits may be slow or failing; compare processing rate with commit rate |
| High replay after restart | Committed offset lags behind processing progress; review count/time and idempotency |
| Commit latency increases | Coordinator/broker overloaded, slow network, or large consumer group |
| Commit errors appear | Check membership, generation, ownership, and coordinator connectivity |

Do not look only at total lag. One partition can fall behind while other partitions remain healthy. Partition-level monitoring helps uncover load skew and unhealthy members.

## 14. Testing COUNT_TIME Behavior

Before deploying, test commit behavior across representative scenarios:

### Count Reached Before Time

Set a small count and a long time. Send enough records faster than the configured time window. Observe that a commit happens once count is reached.

### Time Reached Before Count

Set a large count and a short time. Send a small number of records and wait. Observe that the container commits pending offsets after the time condition is evaluated.

### No New Records

Leave the consumer idle after a commit. **ackTime** expiring should not produce new offset progress if there are no pending offsets.

### Crash Before Commit

Have the listener produce side effects, stop the application before the commit threshold, and restart. Confirm uncommitted records can be re-read and side effects are not applied twice.

### Listener Throws an Exception

Check the error handler, retries, DLT, and offset commits. Confirm failed records are not skipped outside the intended policy.

### Rebalance Before Threshold

Scale consumers or restart a member while offsets are still pending. Observe partition revocation, offset commit behavior, and the new consumer resuming reads.

## 15. Common Misconceptions

**COUNT_TIME waits for both count and time.** Incorrect. It commits when whichever condition is reached first occurs.

**ackTime is an exact deadline guaranteeing offsets are always committed on time.** Incorrect. The container checks the condition during the processing loop; poll, listener, and broker latency can delay commit completion.

**ackCount is the number of times the listener calls acknowledge.** Incorrect. **COUNT_TIME** is container-managed; **ackCount** controls how many records are processed since the previous commit.

**COUNT_TIME commits immediately after every record.** Incorrect. The container accumulates pending offsets until count or time is reached.

**COUNT_TIME guarantees no records are re-read after a crash.** Incorrect. If side effects completed while offsets were uncommitted, records can be re-read.

**COUNT_TIME replaces retries and error handlers.** Incorrect. AckMode controls commits; the error handler controls how failed records are handled.

**ackCount is shared across all consumers in the group.** Incorrect. Each consumer container has its own count and time progress.

**When there are no records, the timer still creates new commits.** With no pending offsets, there is no new progress to commit.

**COUNT_TIME is exactly-once.** Incorrect. It only controls when offsets are committed. Exactly-once in Kafka requires appropriate transactions; side effects in databases or external systems require their own coordination mechanisms.

## 16. Design Guidelines

When choosing **AckMode.COUNT_TIME**, determine the commit overhead and replay window that the business tolerates. Pick **ackCount** to handle high-traffic workloads and **ackTime** to bound commits during low traffic.

A starting setup can be:

1. Set **AckMode.COUNT_TIME** on the listener container.
2. Pick **ackCount** based on actual per-consumer throughput.
3. Pick **ackTime** based on how long the system allows offsets to remain pending.
4. Keep Kafka consumer auto-commit disabled so the container manages offsets.
5. Ensure the listener returns only after side effects reach a safe-to-commit state.
6. Design idempotent processing to tolerate re-read records.
7. Configure error handlers and retries by error category.
8. Verify sync/async commit settings and monitor commit errors.
9. Test crashes, rebalances, low/high traffic, and listener exceptions.
10. Monitor commit rate, commit latency, consumer lag, and replay rate in production.

**COUNT_TIME** is useful when workloads have variable traffic: count commits in batches when many records arrive, while time commits pending progress when traffic is light. Choose both thresholds based on your system's replay tolerance and commit cost; always remember that an offset commit is the consumer group's checkpoint, while side-effect safety must be guaranteed at the business layer.

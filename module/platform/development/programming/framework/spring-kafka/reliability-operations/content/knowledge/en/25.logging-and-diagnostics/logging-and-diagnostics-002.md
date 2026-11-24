# Commit log level

When operating a Spring Kafka consumer, a question frequently arises: **which offset did the consumer commit, at what time, and with what outcome?** This is the core question when a consumer group lags, when records are reprocessed after a restart, when a listener finishes successfully yet offsets do not advance, or when you need to distinguish a normal commit from offsets sent inside a Kafka transaction.

Spring Kafka provides the **commitLogLevel** setting on **ContainerProperties** to control the log level for offset commit information emitted by the listener container. For example, you can promote offset commit information from DEBUG to INFO during a diagnostic window. However, a log line containing an offset is **not absolute proof** that the entire business operation succeeded or that the broker durably recorded the offset. To draw the right conclusion, you must understand **AckMode, sync/async commit, retry/recovery, rebalancing, and transactional offset commits**.

This lesson belongs to the **Logging and Diagnostics** chapter in the **Spring Kafka Reliability Operations** module. It focuses on how to configure the commit log level, read logs, determine which offset was committed, control noise, combine metrics, and build an investigation workflow when logs do not match consumer group state.

## 1. Why observe offset commits?

A Kafka consumer processes records based on offsets per **topic-partition**. The consumer group maintains a committed offset so subsequent runs know where to resume reading.

Example:

~~~text
Topic: orders.events
Partition: 2

Offset 100 -> OrderCreated
Offset 101 -> OrderPaid
Offset 102 -> OrderCancelled

Consumer successfully processes offset 100
       |
       v
Commit offset 101
       |
       v
On restart, consumer group resumes from offset 101
~~~

In Kafka, the committed offset is **the next position to read**, not the offset of the last processed record. If the record at offset 100 was processed with no gap, the consumer typically commits **101**, not 100.

In production, diagnostics need to know:

- Did the record reach the listener?
- Did the listener finish or throw an exception?
- Did the container decide to commit the offset?
- Did the commit use sync or async?
- Did the broker/coordinator acknowledge the commit?
- Which offset does the consumer group actually store?
- Did a rebalance, crash, or transaction abort prevent offsets from advancing?

Commit logs are a useful signal, but they cannot answer all of these questions alone.

## 2. What is commit log level?

**commitLogLevel** is a property on Spring Kafka **ContainerProperties** that specifies the log level used for offset commit information emitted by the listener container.

In many Spring Kafka versions, offset commit information is logged at **DEBUG** by default. To observe it at INFO, you can call:

~~~java
containerProperties.setCommitLogLevel(
    LogIfLevelEnabled.Level.INFO
);
~~~

The **LogIfLevelEnabled.Level** enum belongs to Spring Kafka's logging support API.

Distinction:

| Setting | Which layer does it live in? | Function |
|---|---|---|
| ContainerProperties.commitLogLevel | Spring Kafka listener container | Specifies the log level used for the container's commit info |
| logging.level.org.springframework.kafka.listener | Spring Boot logging backend | Controls whether the logger emits messages at that level |
| syncCommits | Spring Kafka container | Chooses commitSync or commitAsync in the normal commit flow |
| AckMode | Spring Kafka container | Determines when the container considers offsets eligible to commit |
| enable.auto.commit | Kafka consumer | Determines whether to use Kafka client auto-commit |
| isolation.level | Kafka consumer | Specifies whether the consumer reads transactional data as read_committed or read_uncommitted |

**commitLogLevel does not alter offset semantics, retry policy, or delivery guarantees.** It only changes how information is written to the logging system.

## 3. Both log filtering layers must allow it

A Spring Kafka message only appears if:

1. The container emits the message at the level selected via commitLogLevel.
2. The corresponding logger in the logging backend is enabled at that level.
3. No appender/filter drops the message before writing to console, file, or collector.

Example:

~~~text
commitLogLevel = DEBUG
Logger threshold = INFO

=> Commit DEBUG messages do not appear
~~~

Conversely:

~~~text
commitLogLevel = INFO
Logger threshold = INFO

=> Commit INFO messages can appear
   if the code path performs a commit and no other filter drops it
~~~

Another case:

~~~text
commitLogLevel = INFO
Logger threshold = WARN

=> Commit INFO messages remain hidden
~~~

Therefore, calling setCommitLogLevel(INFO) alone is not enough if the logging system configures WARN for the relevant package.

## 4. Spring Boot configuration example in Java

For listeners using **ConcurrentKafkaListenerContainerFactory**, configure container properties before the factory creates listener containers.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.LogIfLevelEnabled;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties()
        .setCommitLogLevel(LogIfLevelEnabled.Level.INFO);

    return factory;
}
~~~

Attach the factory to the listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.events",
    groupId = "orders-worker",
    containerFactory = "ordersListenerContainerFactory"
)
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Notes:

- Configuration in the factory applies only to containers created from that factory.
- If a listener references another factory, commit log level on this factory has no effect.
- If the application has multiple @KafkaListener factories, configure each factory as needed.
- Verify the API and enum type on your project's exact Spring Kafka version.
- Do not assume a listener that creates a MessageListenerContainer via its own bean automatically uses the default factory.

## 5. Configuring Spring Boot logging level

To allow Spring Kafka listener logs at INFO level, declare:

~~~yaml
logging:
  level:
    org.springframework.kafka.listener: INFO
~~~

An illustrative complete configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker1:9092,broker2:9092
    consumer:
      group-id: orders-worker
      enable-auto-commit: false

logging:
  level:
    org.springframework.kafka.listener: INFO
~~~

The application still needs to call **setCommitLogLevel(LogIfLevelEnabled.Level.INFO)** in the container factory; logging.level does not automatically switch the default commitLogLevel from DEBUG to INFO.

If you want to inspect DEBUG logs without changing commitLogLevel, you can temporarily enable:

~~~yaml
logging:
  level:
    org.springframework.kafka.listener: DEBUG
~~~

However, this can turn on many other debug messages in the listener package, not just offset commit information.

In high-throughput environments, it is usually better to **intentionally select commitLogLevel** and keep the logging category quieter rather than leaving DEBUG enabled for all of Spring Kafka over long periods.

## 6. Narrowing configuration by logger category

When you need to limit log volume, instead of enabling the entire package, you can target the listener container's logging category, for instance:

~~~yaml
logging:
  level:
    org.springframework.kafka.listener.KafkaMessageListenerContainer: INFO
~~~

The actual category name may reflect the class or nested class where the logger is initialized in the running Spring Kafka version. Therefore, before applying in production, inspect the **logger name** on an emitted log line.

Example pattern:

~~~text
2026-11-15 14:00:00 INFO
org.springframework.kafka.listener.KafkaMessageListenerContainer
... commit information ...
~~~

This is an illustrative format. Note that exact category configuration also depends on the logging backend, the class using the logger, Spring Kafka implementation changes, and additional filters.

If you set a narrow logging category and see no messages, check:

1. Is commitLogLevel set to INFO or DEBUG?
2. Which class/package does the actual logger name belong to?
3. Did any commits actually happen?
4. Is an appender dropping INFO?
5. Is the container using the configured factory?

Do not conclude “the consumer is not committing” solely because a log line is missing in one category.

## 7. Default commit log level and production policy

In common Spring Kafka versions, commit logs default to **DEBUG** to avoid flooding application logs in workloads with frequent commits.

For example, a consumer processing 10,000 records/second and committing every record can generate huge amounts of commit-related logs if INFO is enabled.

This impacts:

- I/O to stdout or files.
- Centralized log storage costs.
- Ingest throughput of Fluent Bit/Vector/Logstash.
- Volume and retention in the observability system.
- Readability of critical WARN/ERROR alerts.
- CPU and allocations from log formatting, depending on implementation.

Therefore, prefer:

- **DEBUG** for commit details during normal operations if continuous viewing is unnecessary.
- **INFO** during a diagnostic window with clear scope and time limit.
- **Metrics** to track long-term commit rates and failures.
- **Structured logs** at key boundaries instead of logging every record under heavy traffic.

You do not need to set every commit log to ERROR; as long as the logging backend does not enable DEBUG, default detailed info stays hidden.

## 8. commitLogLevel is not the Kafka consumer log level

Components that can emit commit-related logs:

~~~text
Spring Kafka listener container
      |
      +-- Container commit log (commitLogLevel)
      |
      +-- DefaultErrorHandler / rollback logs
      |
      v
KafkaConsumer.commitSync()/commitAsync()
      |
      +-- Kafka client internal debug/error logs
      |
      v
Kafka group coordinator
      |
      +-- Broker logs / metrics
      |
      v
__consumer_offsets (internal Kafka topic)
~~~

**setCommitLogLevel() does not change the log level of all Kafka client internals and brokers**. If you need to see network requests, offset commit requests/responses, coordinator changes, or Kafka client retry logic, use the corresponding Kafka client and broker logger categories.

Enable client DEBUG only with a clear investigation goal, as logs can be massive and internal logger names/fields vary across Kafka client versions.

## 9. Commit log vs. broker-acknowledged commit

A log line like:

~~~text
INFO ... Committing offsets:
  orders.events-0 -> 101
  orders.events-1 -> 205
~~~

is only a **logical format example**, not the verbatim message across all Spring Kafka versions.

If the message is logged **before** a commit call, it indicates the container is preparing to commit those offsets; it does not confirm the Kafka group coordinator accepted them.

If the message is logged **after** a successful commitSync call, it provides stronger evidence of the client call outcome, yet still does not say all non-Kafka side effects are safe.

If using commitAsync, the method can return before the result callback fires. In that case, a log saying “commit invoked” does not mean “commit completed”.

To conclude the broker recorded the committed offset:

1. Check the outcome of sync commit or async commit callback.
2. Inspect exceptions/failures.
3. Verify the committed offset via consumer group tooling or committed() when appropriate.
4. Cross-check rebalance, transaction, and processing logs.

**Do not bet on the exact word “Committed” or “Committing” in a specific log message version.** Inspect the actual message and code path of the running version.

## 10. Committed offset is the next offset

Suppose partition 1 has records:

~~~text
offset 200 -> R200
offset 201 -> R201
offset 202 -> R202
~~~

The listener processes R200 and R201, and has not processed R202 yet:

~~~text
Last processed = 201
Next offset    = 202
Commit value   = 202
~~~

If the log shows:

~~~text
orders.events-1 => offset 202
~~~

that is usually valid. It **does not mean** the record at offset 202 has been processed.

This easily causes confusion when on-call engineers compare:

- Kafka logs containing the offset of the received record.
- Application logs containing the offset the listener just processed.
- Container commit logs containing the **next offset**.
- Consumer group CLI CURRENT-OFFSET usually containing the committed **next offset**.

All must be read using the same convention.

## 11. TopicPartition is the unit of commit

Offsets do not increment across the whole topic as a single counter. Each partition has its own offset sequence.

Example:

~~~text
orders.events P0: commit 105
orders.events P1: commit 560
orders.events P2: commit 41
~~~

This does not mean P1 processes faster than P0 or received more business events over the same period, because partitions differ in data volume and start time.

When reading commit logs:

1. Identify the topic.
2. Identify the partition.
3. Identify the consumer group/listener instance.
4. Identify the next offset.
5. Cross-check log end offset and business processing success on the same partition.

Do not take the “highest offset” across the topic as consumer group progress.

## 12. AckMode determines when commit logs appear

Spring Kafka listener containers support multiple **AckMode** values. This governs when the container considers offsets eligible to commit.

| AckMode | General rule | Commit logs may appear when |
|---|---|---|
| RECORD | After each successfully processed record | Per record, per container semantics |
| BATCH | After all records in the poll are processed per policy | After a poll batch |
| TIME | Based on a time condition | When timer/processing state meets the condition |
| COUNT | Based on record count | When the threshold is reached |
| COUNT_TIME | Meets either count or time condition | When either threshold occurs |
| MANUAL | Listener acknowledges, container commits per manual workflow | After valid ack and pending offset processing |
| MANUAL_IMMEDIATE | Acknowledge in the right context can commit immediately | Near the time acknowledge is called |

**One commit log for many records is normal.** With AckMode.BATCH, 500 processed records may produce one offset commit per partition rather than 500 log lines.

Conversely, listener invocation count and commit count do not have to match. Do not use commit line count to infer the number of successfully processed records.

## 13. AckMode.RECORD example

Configuration:

~~~java
factory.getContainerProperties().setAckMode(
    ContainerProperties.AckMode.RECORD
);

factory.getContainerProperties().setCommitLogLevel(
    LogIfLevelEnabled.Level.INFO
);
~~~

Suppose the consumer receives three records on the same partition and processes them successfully:

~~~text
Listener processed R10
Container commits next offset 11

Listener processed R11
Container commits next offset 12

Listener processed R12
Container commits next offset 13
~~~

This is a logical description, not a guarantee that every step emits exactly one console log line. Actual output also depends on sync/async mode, error handling, internal batching, logging filters, and consumer lifecycle.

At high throughput, AckMode.RECORD can generate many commits and log lines; choose the mode based on latency, duplicate risk, and throughput, not just log readability.

## 14. AckMode.BATCH example

Configuration:

~~~java
factory.getContainerProperties().setAckMode(
    ContainerProperties.AckMode.BATCH
);
~~~

Suppose a poll returns:

~~~text
Partition 0: offsets 10, 11, 12
Partition 1: offsets 20, 21
~~~

After the listener successfully processes the entire poll:

~~~text
Commit map:
  orders.events-0 -> 13
  orders.events-1 -> 22
~~~

A single commit request can contain offsets for multiple partitions. Do not assume “only one commit log” means the listener processed one record.

If an exception or rollback occurs mid-batch, the error handler can alter processing/commit progress. Do not assume the commit map in this example applies to every failure path.

## 15. MANUAL acknowledgement and commit logs

Manual acknowledgement may be needed when the application wants explicit control over which records are considered complete.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.MANUAL_IMMEDIATE
    );

    factory.getContainerProperties().setCommitLogLevel(
        LogIfLevelEnabled.Level.INFO
    );

    return factory;
}
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders.events",
    containerFactory = "ordersFactory"
)
public void onRecord(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.process(record.value());

    // Acknowledge only after business processing completes.
    acknowledgment.acknowledge();
}
~~~

With MANUAL_IMMEDIATE, acknowledging from the consumer thread can trigger a commit near the call time, depending on syncCommits and container conditions. Acknowledging from another thread can behave differently; check your version and ack ordering rules.

**Do not acknowledge before durable side effects complete just to make commit logs appear sooner.** Doing so can cause the Kafka group to skip the record if the application crashes after ack.

## 16. enable.auto.commit and container commit logs

The Kafka consumer has the **enable.auto.commit** setting, which controls the Kafka client's auto-commit mechanism.

In the standard Spring Kafka listener container model, the container should manage offsets:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
~~~

When auto-commit is enabled, the Kafka client can commit offsets on its own interval without following the container's “business processing succeeded” boundary.

Consequences:

- A commit may occur via the Kafka client rather than the container commit path instrumented by commitLogLevel.
- Spring Kafka commit logs do not fully reflect auto-commits performed by the client.
- Relying on auto-commit in the wrong context can skew desired delivery semantics.

Modern Spring Kafka versions may set enable.auto.commit=false automatically when the application does not override it. Still, in production configs, verify **effective consumer properties** and avoid two uncontrolled commit mechanisms running together.

## 17. syncCommits and commitAsync

The Spring Kafka container can use **synchronous** or **asynchronous offset commits** on the non-transactional commit path.

Example configuration:

~~~java
var props = factory.getContainerProperties();

props.setSyncCommits(true);
props.setCommitLogLevel(LogIfLevelEnabled.Level.INFO);
~~~

Or:

~~~java
props.setSyncCommits(false);
~~~

In modern Spring Kafka versions, syncCommits typically defaults to true; verify the effective value in your running version.

| Mode | Kafka consumer API | Meaning for logs and outcomes |
|---|---|---|
| Synchronous | commitSync | Consumer thread waits for the commit call to finish or throw an error |
| Asynchronous | commitAsync | Commit request is sent; result arrives via callback |

With sync commits, commit failures can appear directly on the execution path. With async commits, you need to instrument the **callback** to distinguish attempted commits from successful/failed ones.

The container's log level does not change the synchronicity or guarantees of the commit.

## 18. A “committed” log does not guarantee commit success

Suppose the logger writes:

~~~text
INFO ... Commit offsets: {orders.events-0=101}
~~~

A commit request can still hit:

~~~text
Coordinator unavailable
Group rebalance in progress
Request timeout
Producer/consumer closed
Authentication/authorization error
~~~

Without knowing whether the log was emitted **before or after** the commit call and without an outcome callback, you cannot conclude the broker confirmed success.

To improve diagnostic reliability:

- Record a commit_attempts metric.
- Record commit_success and commit_failure metrics at the boundary with actual outcomes.
- Capture root exception class and consumer group.
- Cross-check committed offsets using Kafka group tooling.
- Verify listener retries and idempotency on commit failures.

A log is useful for knowing **which offset the container intended to commit**, while the actual committed offset should be verified independently when in doubt.

## 19. commitSync failures and error categories

Several categories of errors can appear during commits:

| Category | Examples | Diagnostic meaning |
|---|---|---|
| Consumer group ownership | CommitFailedException, rebalance-related error | Consumer may no longer hold valid partition/generation ownership |
| Coordinator/network | Timeout/disconnect/coordinator unavailable | Commit request was not acknowledged |
| Authorization | Group authorization failure | Consumer lacks the required permissions |
| Client lifecycle | Wakeup/closed consumer state | Shutdown or control operation at an invalid moment |
| Transactional path | Producer fencing, transaction abort | Offset commit is inside a Kafka transaction rather than a direct consumer commit |

Exact exceptions and how they are wrapped/logged depend on Kafka client/Spring Kafka versions. Do not rely solely on exception class to decide to retry commits indefinitely.

In particular, after **onPartitionsLost** or when a consumer loses its group generation, the application must not attempt to commit offsets as if it were still the old owner.

## 20. Commit logs and rebalancing

When a consumer group changes membership or partitions are reassigned, commits can tie into partition ownership lifecycle.

~~~text
Consumer A processes partition 0
       |
       v
Rebalance starts
       |
       v
Partition is revoked or lost
       |
       v
Container may commit eligible offsets
per phase and policy
       |
       v
Consumer B receives the partition
~~~

A commit log line near a rebalance timestamp does not mean all in-flight records completed.

When investigating:

1. Check timestamps of commit logs and rebalance logs.
2. Cross-check which partitions were revoked/lost.
3. Check whether offsets were recorded or commits failed.
4. Check listener in-flight records and async tasks.
5. Look for redelivered records after reassignment.

With cooperative rebalancing or static membership, how partitions transfer owners differs from eager rebalancing. Do not infer from missing commit logs that no rebalance occurred.

## 21. Commit logs and graceful shutdown

Upon receiving SIGTERM, a Spring Kafka listener container is normally stopped via the Spring lifecycle. The container can finish in-progress processing and commit eligible offsets before closing the consumer.

Example:

~~~text
Container processes record offset 500
      |
      v
SIGTERM received
      |
      v
Listener finishes the record
      |
      v
Container commits next offset 501
      |
      v
Consumer closes
~~~

This is the ideal shutdown path. In practice:

- The Kubernetes grace period may expire before the commit finishes.
- The listener may be stuck in an HTTP/database call.
- The producer or broker may time out.
- The commit may fail due to a rebalance.
- The process may be OOMKilled or SIGKILLed without running shutdown hooks.

**Not seeing a final commit log** after a crash does not automatically prove the Kafka offset was not committed; the log pipeline may simply not have flushed. Conversely, **seeing a commit line before SIGKILL** does not prove business side effects are idempotent.

## 22. Commit logs in a transactional listener

When a Spring Kafka listener container uses a Kafka transaction manager, committing consumed offsets can happen by **including offsets in the same Kafka transaction as the output**.

~~~text
Input Kafka record
      |
      v
Begin Kafka transaction
      |
      +-- Listener sends Kafka output
      |
      +-- Container adds consumed offsets to transaction
      |
      v
commitTransaction()
      |
      +-- Commit success:
      |      Kafka output and consumed offsets are committed together
      |
      +-- Abort:
             Transactional output is hidden from read_committed
             Consumed offsets in the transaction are not committed
~~~

In this case, do not expect a direct Consumer.commitSync log to appear the same way as in a non-transactional listener. The container may use producer transaction APIs, and the final outcome depends on **committing/aborting the transaction**.

commitLogLevel only controls commit-related logs at the Spring Kafka container per implementation. To accurately diagnose the EOS path, observe:

- Transaction begin/commit/abort.
- Producer fencing or transaction timeout.
- sendOffsetsToTransaction behavior.
- Output topic visibility for read_committed consumers.
- Committed input group offsets.

Kafka transactions do not automatically include database or HTTP side effects; do not treat “Kafka transaction committed” as proof that a database operation was atomic with Kafka.

## 23. When a transaction aborts after the listener ran

Suppose:

~~~text
Listener processed OrderCreated
      |
      +-- External database update succeeded
      |
      +-- Kafka output inside transaction
      |
      v
Kafka transaction timeout -> abort
      |
      v
Input offset not committed with transaction
      |
      v
Record is read again
~~~

Here you may see a listener success log and a transaction abort log within the same timeframe. Looking only at listener success or a commit-intent line could mislead an operator into believing the record completed.

Hence, there are three separate questions:

1. Did the listener method return without error?
2. Did the Kafka transaction/offset commit finish?
3. Are side effects outside Kafka idempotent?

commitLogLevel does not answer the third question.

## 24. DefaultErrorHandler and recovery

For non-transactional listeners, when a record throws an exception, **DefaultErrorHandler** can retry or invoke a recoverer to send the record to a DLT.

~~~text
Listener processes offset 100 -> error
       |
       v
DefaultErrorHandler
       |
       +-- Retry
       |      |
       |      v
       |   Reprocess
       |
       +-- Retries exhausted / non-retryable
              |
              v
       DeadLetterPublishingRecoverer
              |
              v
       DLT publish confirmed successful
              |
              v
       Source offset can advance per policy
~~~

A commit log after recovery does not prove **the original business logic succeeded**. It may simply indicate the container handled the record under the error policy, such as routing it to a DLT and moving past it on the source topic.

When investigating, inspect:

- Error handler classifications and backoff.
- Retry attempts.
- DLT publish success/failure.
- ackAfterHandle/commitRecovered behavior per version/config.
- Source offset commit outcome.
- DLT consumer backlog and manual review.

Do not turn on commitLogLevel INFO and treat advancing offsets as proof that there are no poison records.

## 25. Failed recovery and why commits must not skip the record

Suppose the DLT producer encounters an authorization error:

~~~text
Listener hits poison record
       |
       v
Recoverer attempts to publish to DLT
       |
       v
DLT send fails
       |
       v
Record cannot be considered safely recovered
       |
       v
Record must be reprocessed or retained per policy
~~~

If the application commits the offset anyway to clear lag despite failed recovery, the record can be skipped and disappear from the consumer group's normal processing path.

To avoid **silent loss**, when reading commit logs near the error handler:

1. Verify whether the recovery operation had a successful outcome.
2. If using an async producer, check the send future/callback.
3. Check which ack policy governed the source commit.
4. Confirm the DLT topic/record exists if recovery relies on a DLT.
5. Do not infer from advancing offsets that all records completed business processing.

## 26. Commit logs and batch listeners

A batch listener can receive multiple ConsumerRecords at once:

~~~java
@KafkaListener(
    topics = "orders.events",
    containerFactory = "ordersBatchFactory"
)
public void handleBatch(List<OrderEvent> batch) {
    orderService.processBatch(batch);
}
~~~

If the method receives 200 records:

- One batch listener invocation can process 200 records.
- The commit map may hold next offsets for multiple partitions.
- An exception can trigger batch retry or recovery per configuration.
- The database may have partially applied work without transactions/idempotency.

Do not use **the number of commit logs** as a metric for successful records. For batch workloads, also track:

- Batch size.
- Batch processing latency.
- Batch failure count.
- Record success/failure metrics if available.
- Committed offset per partition.
- Redeliveries after errors/rebalances.

An offset commit advancing by 200 does not prove 200 independent business side effects were safely committed.

## 27. Why can offset logs jump by many units?

Suppose the commit log shows:

~~~text
12:00:01 P0 commit 1.000
12:00:02 P0 commit 1.500
12:00:03 P0 commit 2.000
~~~

An offset jump of 500 can be completely normal when:

- Using AckMode.BATCH.
- Polls/processing handle many records.
- Commits are coalesced by count/time.
- The consumer drains backlog faster than the commit cadence.

However, if the application calls seek/commit improperly, an offset jump can signal skipped data.

To tell them apart, compare:

- Container AckMode.
- max.poll.records.
- Number of delivered/processed records.
- Error handler recovery/seeks.
- Manual acknowledgement behavior.
- Application-level seek/reset operations.

Do not claim “data loss” solely from two log lines with a large offset gap.

## 28. Why might offset logs stop advancing?

A commit log repeating the same offset or stopping completely can be caused by:

- No new records on the topic.
- The consumer has caught up.
- The container is paused/stopped.
- The consumer has no assigned partitions.
- The listener is spending a long time processing a record.
- AckMode.TIME/COUNT has not reached its threshold.
- Manual ack has not been called.
- The error handler is retrying a poison record.
- Transaction aborts.
- Commit requests are failing.
- Logger filtering.

Conclusions must rest on **multiple signals**, not a single logger.

Example:

~~~text
Consumer lag = 0
No new input records
No commit logs for 10 minutes

=> May be completely normal
~~~

Conversely:

~~~text
Consumer lag = 50.000
High producer input rate
Listener success rate near 0
No commit logs for 10 minutes

=> Must investigate pause, retries, poll, and dependencies
~~~

## 29. Commit log level does not control commit frequency

A common misconception:

~~~text
commitLogLevel = INFO
=> Kafka commits more frequently
~~~

This is **false**. That parameter only controls the **log level**; it does not change:

- AckMode.
- syncCommits.
- enable.auto.commit.
- ackCount/ackTime.
- Listener throughput.
- Kafka transaction commits.
- Retry or DLT policies.

To adjust commit frequency, evaluate the container's acknowledgement/commit policy and delivery semantics requirements; do not tweak the log level.

## 30. Logging pattern for diagnostics

A useful log line should include:

~~~text
time=2026-11-15T14:00:00Z
level=INFO
logger=org.springframework.kafka.listener.KafkaMessageListenerContainer
service=order-service
instance=orders-pod-3
listener=orders-listener
group=orders-worker
topic=orders.events
partition=2
nextOffset=501
action=commit_requested
~~~

This is a **recommended instrumentation format**, not verbatim default Spring Kafka output.

When capturing outcomes:

~~~text
action=commit_succeeded
commitMode=sync
group=orders-worker
topic=orders.events
partition=2
nextOffset=501
elapsedMs=12
~~~

If using a Logback JSON encoder or OpenTelemetry logging, you can attach appropriate MDC/correlation fields. However, do not assume the Spring Kafka container automatically copies all listener MDC into commit logs, especially when commit callbacks run on a different thread.

## 31. Correlation between processing and commits

An investigation often needs to connect:

~~~text
Listener received offset 500
       |
       v
Business processing success
       |
       v
Container commit requested next offset 501
       |
       v
Commit completed
~~~

Have dedicated structured logs at application boundaries:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(
        ConsumerRecord<String, OrderEvent> record) {

    log.info(
        "kafka_delivery_started topic={} partition={} offset={}",
        record.topic(),
        record.partition(),
        record.offset()
    );

    orderService.process(record.value());

    log.info(
        "kafka_business_processed topic={} partition={} offset={}",
        record.topic(),
        record.partition(),
        record.offset()
    );
}
~~~

These logs illustrate how to correlate; do not enable INFO per record on very high-volume workloads without a sampling/retention policy. And business_processed only indicates the method returned cleanly; side-effect durability must be defined at the business layer.

Container commit logs show the step after the listener, but **do not create a distributed transaction** between Kafka commits and databases/HTTP calls.

## 32. MDC and listener concurrency

When a Kafka listener has concurrency > 1, records are processed across different consumer threads.

~~~text
orders-listener
  +-- consumer-0 => P0,P3
  +-- consumer-1 => P1,P4
  +-- consumer-2 => P2,P5
~~~

A log line should carry:

- Listener ID.
- Consumer group.
- Consumer client ID/instance when available.
- Topic-partition.
- Offset.
- Thread name or trace context.

With MDC:

~~~java
try {
    MDC.put("kafka.topic", record.topic());
    MDC.put("kafka.partition", Integer.toString(record.partition()));
    MDC.put("kafka.offset", Long.toString(record.offset()));

    orderService.process(record.value());
}
finally {
    MDC.remove("kafka.topic");
    MDC.remove("kafka.partition");
    MDC.remove("kafka.offset");
}
~~~

MDC has thread-local semantics in many logging backends; clean up in finally so subsequent records do not inherit stale context. With async listeners, MDC context must be propagated intentionally. Commit logs emitted by Spring Kafka may not run inside this exact MDC scope, so do not rely on MDC as the sole way to identify commits.

## 33. Do not log sensitive payloads to explain commits

To understand offset commits, you usually only need:

- Topic.
- Partition.
- Offset/next offset.
- Group.
- Timestamp.
- Commit mode and outcome.
- Non-sensitive correlation ID.

Do not print:

- Full payloads containing customer information.
- Authorization headers/credentials.
- Kafka keys containing sensitive identifiers.
- Database secrets.
- HTTP bearer tokens.

A commit log itself may not contain payloads, but surrounding application logs/exception messages might inadvertently leak data. When enabling DEBUG in production, review logger category scopes and the log collector's data protection policies.

## 34. Differences between logs and metrics

Logs are useful for inspecting specific offsets:

~~~text
P2 offset 501 was scheduled for commit by the container at 14:00:00
~~~

Metrics are useful for observing trends:

~~~text
Are commit attempts/sec rising or falling?
Are commit failures spiking?
What is commit latency p99?
Is group lag growing?
~~~

Do not replace metrics by counting log lines containing the word “commit”. A commit log can:

- Cover multiple partitions.
- Be lost due to sampling/collector outages.
- Be filtered by logging levels.
- Represent requested rather than successful commits.
- Change message wording across versions.

Instead of relying on log parsing as the sole data source, prefer Kafka client/JMX/Micrometer metrics and instrumentation with explicit outcomes.

## 35. Metrics to pair with commit logs

| Metric | Interpretation |
|---|---|
| records_consumed_rate | Whether the consumer receives records fast or slow |
| listener_success_rate | How many business listener executions succeed |
| listener_failure_rate | Whether processing errors are increasing |
| consumer_group_lag | How far committed offsets trail log end |
| commit_attempt_rate | How often the container/client attempts commits |
| commit_failure_rate | How many commits fail |
| commit_latency_p95/p99 | How slow commit requests/callbacks are |
| rebalance_count/duration | Whether consumer ownership churns frequently |
| paused_partition_count | Whether pauses are freezing offsets |
| retry_count | Whether failing records are being retried |
| recovery/DLT_count | Whether records are skipped after recovery |
| transaction_abort_rate | Whether transactional offset commits are failing |
| last_successful_commit_age | Time since the last confirmed commit |

Some of the metric names above are **custom concepts** rather than fixed Kafka client/Micrometer names. When the Kafka client already provides equivalent metrics, use those before inventing another metric with unclear semantics.

## 36. Kafka CLI to verify committed offsets

One way to inspect a consumer group:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --group orders-worker \
  --describe
~~~

Example output:

~~~text
TOPIC          PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG
orders.events  0         101            140            39
orders.events  1         205            205             0
orders.events  2         501            550            49
~~~

**CURRENT-OFFSET** is the consumer group's committed next offset as presented by the CLI. If the latest container log says P2 intended to commit 501 and the CLI also shows 501, that is a consistent sign. Still, account for sampling timing; the CLI snapshot could occur before or after a new commit.

If the CLI still shows 480:

1. Check whether the log showed commit intent or confirmed commit.
2. Check for commit failures.
3. Verify you are looking at the right consumer group.
4. Verify topic/partition.
5. Check for offset resets/rebalances between the two reads.
6. Confirm you are not checking the wrong environment/cluster.

Do not manually reset offsets via CLI to “sync” with logs before understanding which records were processed and which side effects occurred.

## 37. Commit logs and isolation.level=read_committed

A consumer using **read_committed** can be bounded by the **Last Stable Offset (LSO)** when a Kafka transaction remains open.

~~~text
Log End Offset (LEO) advances
       |
       v
An earlier transaction is still open
       |
       v
LSO lags behind LEO
       |
       v
read_committed consumer cannot read past LSO yet
       |
       v
Consumer may receive no new records
       |
       v
No new commit logs appear
~~~

That alone does not prove the consumer is broken. When investigating “commit logs not advancing while lag is high”, check:

- isolation.level.
- Open transactions and transaction timeouts.
- LSO/HW/LEO if monitoring exposes them.
- Producer commit/abort rates.
- Consumer poll responsiveness.

A lag dashboard measured against LEO can climb even while a read_committed consumer cannot yet read records beyond LSO.

## 38. Logging in Kubernetes environments

Containerized Spring Boot apps typically write logs to stdout for collector ingestion. Enabling commitLogLevel.INFO can drastically increase log volume across multi-replica rollouts.

Example:

~~~text
10 pods
100 commits/second/pod
= 1,000 commit-related events/second
~~~

If each log event is 500 bytes:

~~~text
1,000 × 500 = 500,000 bytes/second
≈ 43 GB/day before compression and overhead
~~~

This is an **illustrative estimate**, not a fixed byte count for Spring Kafka. Still, it shows how a single log level change can impact cost.

When enabling INFO for commit diagnostics:

- Scope it to the service/listener under investigation.
- Use sampling if supported by the backend while preserving correlation.
- Set a deadline to turn it back off.
- Define log retention.
- Monitor log ingest rate.
- Avoid drowning out critical alerts.

A log volume budget should be part of the change plan.

## 39. Dynamic log levels via Spring Boot Actuator

Spring Boot Actuator can manage logger levels at runtime when the endpoint is enabled and properly secured. For example, **/actuator/loggers** can allow changing the configured level of a logger category.

This helps when you do not want to restart a service just to investigate.

However, understand the two layers:

1. Actuator adjusts the **backend logger level**.
2. ContainerProperties.commitLogLevel determines **the level at which the container emits commit logs**.

If commitLogLevel remains DEBUG, turning the logger to DEBUG makes commit logs appear while also enabling other DEBUG logs in the same category. If commitLogLevel is INFO, switching the backend logger threshold to DEBUG does not turn commit messages into DEBUG; they still emit at the configured commitLogLevel.

Never expose the log-level endpoint publicly. Enforce authentication/authorization, auditing, and rollback when the incident ends. Dynamic logger changes do not necessarily alter commitLogLevel on an already-running container.

## 40. commitLogLevel is an observation choice, not a fix

For example, consumer lag grows due to a database deadlock:

~~~text
Database lock
    |
    v
Listener blocked
    |
    v
Offset never reaches commit condition
    |
    v
No new commit logs
~~~

Switching commitLogLevel from DEBUG to INFO **does not release the database lock** and does not help the consumer catch up on backlog. It only lets you see offsets when the container actually performs commits.

To resolve it:

- Diagnose listener processing latency.
- Check database locks/statement timeouts.
- Check max.poll.interval.ms and rebalancing.
- Check error handler retries/transactions.
- Ensure idempotency on redelivery.

Logging is an observation tool; it does not alter semantics or business root causes.

## 41. Case: “listener succeeds yet no commit log appears”

Symptom:

~~~text
14:00:00 Business processed R100
14:00:01 Business processed R101
14:00:02 Business processed R102
No container commit logs
~~~

Investigate in order:

1. What is commitLogLevel set to?
2. Is the backend logger enabled at that level?
3. Which factory does the listener container use?
4. Is AckMode BATCH/TIME/COUNT?
5. Have ackCount/ackTime thresholds been met?
6. Is enable.auto.commit accidentally enabled?
7. Are consumer group offsets advancing in the CLI?
8. Is a Kafka transaction committing offsets via the producer?
9. Is log collection dropping or sampling logs?

Do not trigger retries or replays just to “generate new logs” before checking these questions.

## 42. Case: “commit logs appear yet lag does not drop”

Symptom:

~~~text
Commit logs appear continuously
Consumer group lag keeps rising
~~~

Possible causes:

- Producer ingress rate exceeds consumer commit rate.
- Commits stay at low offsets even though called frequently.
- The logger prints before commit while commits are actually failing.
- The lag dashboard points to a different group/topic.
- One partition is stuck while other partitions advance.
- The consumer is re-reading records due to commit failures/rebalances.
- LEO grows rapidly while processing throughput stays flat.
- read_committed LSO/metric definitions create a discrepancy.

Compare the **delta of committed offset** against the **delta of log end offset** per partition, rather than just counting commit occurrences.

## 43. Case: “commit log says 501 yet CLI says 500”

Not necessarily bad data.

Hypotheses:

1. The log described commit intent, and the actual commit failed.
2. The CLI snapshot ran before the commit finished.
3. You are inspecting the wrong consumer group.
4. The log came from another instance, environment, or partition.
5. An asynchronous commit has not been acknowledged yet.
6. A Kafka transaction has not committed or was aborted.
7. A subsequent reset/seek/administrative offset change occurred.

Checklist:

~~~text
same Kafka cluster?
same consumer group?
same topic-partition?
same observation time?
commit outcome known?
transaction committed?
rebalance occurred?
~~~

Only draw conclusions after verifying all of these items.

## 44. Case: “offset commits fail repeatedly”

When commit failures spike:

1. Inspect the root exception and consumer group coordinator.
2. Check rebalance frequency and max.poll.interval.ms.
3. Check whether the listener has overly long blocking calls.
4. Check broker/network latency.
5. Check group authorization and credential rotation.
6. Check whether lifecycle stop/close/wakeup happened nearby.
7. If transactional, check producer fencing/transaction aborts.
8. Check whether source offsets are redelivering.
9. Ensure business handlers are idempotent before retries/replays.

Do not try calling commitSync endlessly from a non-consumer thread to “catch up” while the coordinator is rebalancing. KafkaConsumer is not thread-safe for concurrent multi-thread access.

If the group lost partition ownership, records may need to be reprocessed on the new owner starting from the valid committed offset.

## 45. How to collect diagnostic logs during an incident

A safe workflow:

**Step 1 — Define the goal**

Do you need to see next offsets for which partition, or inspect commit failure outcomes?

**Step 2 — Narrow the scope**

Select the service, consumer group, listener ID, topic-partition, and time window.

**Step 3 — Enable appropriate logs**

If you only need offsets the container intends to commit, configure commitLogLevel and the backend logger appropriately. If you need request/response internals, enable client DEBUG within a strict scope.

**Step 4 — Build a timeline**

Record listener delivered/processed, error handler, commit intent/outcome, rebalances, and transactions.

**Step 5 — Cross-check the broker**

Run consumer-groups describe or use group offset metrics to verify committed offsets.

**Step 6 — Restore log policy**

Lower logging levels after the incident, retain necessary traces/metrics, and document findings in the runbook.

Permanently enabling verbose logs is rarely better than metrics paired with time-boxed incident diagnostics.

## 46. Relatively complete diagnostic configuration example

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
diagnosticOrdersFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    var props = factory.getContainerProperties();

    // Commit after completing the poll batch.
    props.setAckMode(ContainerProperties.AckMode.BATCH);

    // Use synchronous consumer commits when non-transactional.
    props.setSyncCommits(true);

    // Promote container commit messages to INFO for the investigation window.
    props.setCommitLogLevel(LogIfLevelEnabled.Level.INFO);

    return factory;
}
~~~

Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-worker
      enable-auto-commit: false
      max-poll-records: 200

logging:
  level:
    org.springframework.kafka.listener: INFO
~~~

If using a transactional container, configure the appropriate Kafka transaction manager and interpret offset commits along the transactional path rather than assuming setSyncCommits determines the outcome.

This example is for logging and diagnostics, not a recommendation that every production consumer use BATCH + syncCommits + INFO. Choose settings based on SLOs, load, and delivery requirements.

## 47. Combining logs with Retry/Recovery metrics

A record may go through retries and then recovery:

~~~text
Offset 100 -> listener fails
      |
      v
Retry 1 -> fails
      |
      v
Retry 2 -> fails
      |
      v
DLT publish succeeds
      |
      v
Container progresses source offset to 101
~~~

A commit log for next offset 101 does not tell you:

- How many retries executed.
- Why the listener failed.
- Whether the DLT publish was truly confirmed.
- Whether the DLT consumer processed the record.

Track metrics such as:

- listener_attempts_total.
- retry_attempts_started_total.
- recovery_attempts_total.
- recovery_succeeded_total.
- dlt_publish_confirmed_total.
- committed_offset_progress.

These metric names are illustrative, not all built-in. Distinguish recovery success from business success so commit progress does not mask business failures.

## 48. Quick diagnostic reference table

| Signal | Likely explanation | What else to check |
|---|---|---|
| Commit INFO logs appear steadily | Container is traversing the commit logging path | Broker outcome/CLI, listener success |
| No commit logs appear | Logger filtered, no commits yet, or transactional path | AckMode, logger, transaction, CLI |
| Commit offset grows slowly | Slow processing or few records | Input rate, lag, listener latency |
| Commit offset jumps sharply | Batch processing or high volume | AckMode, record count, recovery |
| Commit log present while commit failed metric rises | Log may only indicate intent | Async callbacks, exceptions |
| Committed offset flat and lag rising | Consumer not making progress | Pause, retries, rebalance, dependencies |
| Committed offset flat and lag=0 | Likely no new input | Producer rate/assignment |
| Transaction aborts rising | Offsets/output may not commit | Producer timeout/fencing, read_committed |
| DLT recovery rising and commits rising | Errors may be routed to DLT | DLT backlog and business outcome |
| Rebalances rising alongside commit failures | Ownership/group generation churn | max.poll.interval.ms, assignor, lifecycle |

## 49. Testing commit log level

Testing has two goals: verifying the **configured log level** and verifying **how logs are interpreted**.

### 49.1. Default DEBUG is filtered

Run the listener container in a test environment with the logger threshold at INFO and commitLogLevel left at its version default. Verify you do not treat the absence of commit logs as a commit failure; inspect committed offsets separately.

### 49.2. Enabling commitLogLevel.INFO

Set the container property to INFO and the backend logger to INFO. Publish a record, wait for the listener to process it successfully, and verify commit logs appear per implementation/version.

### 49.3. Logger WARN blocks commit INFO

Keep commitLogLevel.INFO while setting the backend logger to WARN. Verify commit behavior remains unchanged even though commit INFO messages no longer appear.

### 49.4. AckMode.RECORD vs. BATCH

Send multiple records from a single poll. Observe commit counts/offset samples and verify committed offsets. Do not enforce log line count strictly equal to record count.

### 49.5. Manual acknowledgement

Set MANUAL_IMMEDIATE; let the listener process and acknowledge. Verify commits after ack and the case where no ack occurs before process termination.

### 49.6. Commit failure

Simulate a broker/coordinator or group membership error in a test cluster. Verify an attempted log is not treated as success and that metrics/callbacks reflect the exception.

### 49.7. Transactional listener

Send transactional output and consumed offsets in the same transaction, then force an abort. Verify read_committed visibility and committed source offsets without using direct commit logs as the sole check.

### 49.8. Rebalance and shutdown

Trigger a rebalance or terminate an instance in a test. Verify offset behavior/duplicate handling and avoid concluding a log line before a crash guarantees the commit completed.

These tests belong to the application's own integration test suite, not a requirement to run Gradle or test projects while authoring lesson content.

## 50. Common configuration mistakes

| Practice | Problem | Adjustment |
|---|---|---|
| Setting only logging.level=INFO | Default DEBUG commit logs stay hidden | Set commitLogLevel(INFO) if INFO is wanted |
| Setting only commitLogLevel(INFO) | Backend logger at WARN still filters messages | Configure a compatible logger threshold |
| Setting on a factory unused by the listener | No effect on the target listener | Verify containerFactory |
| Enabling DEBUG on all Kafka clients across prod | Massive logs, hard to investigate | Choose specific category and time limit |
| Counting log lines as successful commits | Log may be intent or cover multiple partitions | Observe outcomes and group offsets |
| Counting log lines as processed records | AckMode.BATCH/TIME breaks 1:1 mapping | Measure listener records separately |
| Assuming commit offset N means record N processed | Kafka commits store next offset | Compare lastProcessed=N-1 |
| Leaving enable.auto.commit on unintentionally | Client and container semantics can diverge | Let the container manage offsets |
| Calling commitSync from another thread | KafkaConsumer is not generally thread-safe | Use container APIs |
| Treating transactional output+offset as direct consumer commit | Misunderstands EOS path | Inspect producer transaction outcomes |
| Counting post-DLT commits as business success | Poison record was not processed by business logic | Separate DLT/business metrics |
| Checking only total lag | A stuck partition can be masked | Inspect offsets per partition |
| Ignoring rebalances | Mistakes lost ownership for commit failures | Check assign/revoke/lost events |
| Turning on verbose logs and forgetting to turn off | Increases long-term logging cost | Incident scope and level rollback |
| Putting payloads/tokens into logs | Exposes sensitive data | Log only required metadata |

## 51. Runbook: no commit logs appearing

**Step 1 — Check container state**

Is the listener container running? Does it have assigned partitions? Is it paused or rebalancing?

**Step 2 — Check log configuration**

Is commitLogLevel DEBUG or INFO? Is the backend threshold INFO/DEBUG/WARN? Does an appender filter or sample logs?

**Step 3 — Check container factory**

Does @KafkaListener use the right factory? Was the configuration applied before container startup?

**Step 4 — Check commit semantics**

What is AckMode? Is enable.auto.commit disabled? Did the listener call manual acknowledge? Is it on a transactional path?

**Step 5 — Cross-check the Kafka group**

Is Kafka CLI CURRENT-OFFSET advancing? If yes, a logging gap does not mean a commit gap.

**Step 6 — Cross-check processing**

What are listener success rate, failures, retry/DLT counts, lag, last record age, and poll responsiveness?

**Step 7 — Take action**

Adjust logging temporarily if visibility is all that is missing. If commits are truly stuck, fix the root cause in listener, ack, broker/group, or transactions.

## 52. Runbook: commit failures increasing

**Step 1:** Determine sync vs. async commit; obtain actual error outcomes.

**Step 2:** Inspect group coordinator, network, ACL, and consumer client logs.

**Step 3:** Check max.poll.interval.ms and listener processing time.

**Step 4:** Correlate rebalance/revocation timestamps with commit failures.

**Step 5:** If transactional, check transaction timeout, producer fencing, and commit/abort state.

**Step 6:** Check whether records are redelivered; protect database/HTTP side effects with idempotency.

**Step 7:** Verify group offsets and consumer lag after remediation.

Never force-commit past unprocessed records just to make logs or dashboards show lag dropping.

## 53. Runbook: commit logs advance yet business data is missing

A flow can commit offsets after a recoverer sends records to a DLT. If downstream does not process the DLT, users may report “missing” business records even though Kafka group lag is 0.

To investigate:

1. Identify the record's source offset and key/event ID.
2. Inspect listener attempts and failures.
3. Inspect DefaultErrorHandler/recovery classification.
4. Verify DLT publication and DLT consumer progress.
5. Inspect business database/side effects.
6. Check whether manual acknowledgements were called prematurely.
7. Inspect transaction boundaries and offset commit order.
8. Design idempotent DLT replay once the data error is fixed.

**Zero consumer group lag does not guarantee 100% of business events succeeded.** It only reflects offset progress as stored by the group.

## 54. Checklist before enabling commitLogLevel.INFO

1. Have you identified the exact listener container and consumer group to investigate?
2. Is ContainerProperties.commitLogLevel configured with the right API for your Spring Kafka version?
3. Does the backend logger threshold allow INFO?
4. Has the actual logger category been verified from logs?
5. Does the listener use that exact ConcurrentKafkaListenerContainerFactory?
6. Is enable.auto.commit configured in line with offset ownership?
7. Are AckMode and syncCommits accurately understood?
8. If using manual ack, does the listener ack only after successful processing?
9. If using Kafka transactions, are commit/abort and sendOffsetsToTransaction tracked?
10. Do you know whether the log describes commit intent or a confirmed outcome?
11. Are Kafka CLI/consumer group metrics available to verify committed offsets?
12. Have you distinguished committed next offset from last processed record offset?
13. Are retry/recovery/DLT metrics paired so commits are not confused with business success?
14. Is consumer lag observed per partition, not only group total?
15. Are logs/metrics available for rebalances, pauses, shutdowns, and commit failures?
16. Are correlation IDs standardized and payloads/secrets kept out of logs?
17. Have log volume/ingest costs been estimated when enabling INFO?
18. Are scope, owner, and deadline to disable verbose logging defined?
19. Have sync/async, AckMode, commit failures, and transactional aborts been tested in a test environment?
20. Are runbooks ready for missing commit logs, failed commits, or advancing commits with business failures?

## 55. Conclusion

**Commit log level** is an observation tool of the Spring Kafka listener container, primarily configured via **ContainerProperties.setCommitLogLevel(LogIfLevelEnabled.Level)**. It promotes offset commit information to an appropriate log level, such as INFO during an incident. However, messages appear only when the logging backend also permits them, and seeing a commit log does not automatically prove the broker acknowledged the offset, every record succeeded, or external non-Kafka side effects committed atomically.

For reliable diagnostics, read logs in terms of **topic-partition-next offset**, understand **AckMode**, distinguish **commitSync** from **commitAsync**, watch **rebalances/retries/recovery**, and handle **Kafka transactional offset commits** separately. Then cross-check with consumer group committed offsets, retry/DLT outcomes, transaction metrics, and actual business state.

In production, the best practice is to **use verbose logs with clear time limits and scope for investigation**, rely on metrics for long-term trends, and always protect consumers with idempotency so the system remains correct when commits fail or records must be reprocessed.

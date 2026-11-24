# Retryable Topic Pattern

When a Kafka listener fails to process a record, the traditional retry approach is to hold the record on the current partition and retry after a backoff period. This approach is called **blocking retry**: the consumer thread must wait for the retry attempt, blocking subsequent records on that partition.

Spring Kafka provides **non-blocking retry** using retryable topics. When a listener fails, the framework publishes the record to a retry topic scheduled for an appropriate processing time, allowing the main topic consumer to continue receiving other records. Another listener processes the retry topic when the wait time has elapsed; if it continues to fail, the record is forwarded to the next retry topic or to a dead-letter topic (DLT).

This pattern is suitable when temporarily failed records need to be isolated from the main flow and it is acceptable that processing order across records may change. It is especially useful when downstream dependencies need time to recover while the application continues processing independent events.

## 1. Why Do We Need Retryable Topics?

Suppose the `orders.created` topic has three records in order:

```text
orders.created, partition 0
  offset 10: order A
  offset 11: order B  -- processing failed due to inventory service timeout
  offset 12: order C
```

With blocking retry, the consumer keeps processing stuck at record B during retries. Record C must wait until B succeeds or is recovered. If B needs to wait 30 seconds, subsequent records on the partition are delayed as well.

With non-blocking retry, when B fails, the framework sends B to a retry topic and acknowledges progress on the original topic once forwarding succeeds. The main topic consumer can continue with C. B will be reprocessed on the retry topic after the configured delay.

This prevents a temporarily failing record from blocking the entire partition, but introduces a trade-off: record C may be processed before B. Non-blocking retry does not preserve global processing order across records in the original partition.

## 2. Topology of Retryable Topics

A retryable topic flow typically consists of three types of topics:

- **Main topic:** the original business topic, for example `orders.created`.
- **Retry topics:** intermediate topics holding records to be retried after different delay intervals.
- **Dead-letter topic:** the destination for records after exhausting retry attempts or when no suitable retry path remains.

```text
                         success
                    +--------------------> processing complete
                    |
orders.created ---> Main listener
                    |
                    | failure
                    v
              orders.created-retry-0
                    |
                    | retry time reached
                    v
              Retry listener 0
                    |
              +-----+------+
              |            |
          success       failure
              |            |
              v            v
          complete    orders.created-retry-1
                            |
                            v
                      Retry listener 1
                            |
                       +----+----+
                       |         |
                   success   failure/attempts exhausted
                       |         |
                       v         v
                   complete   orders.created-dlt
```

Topic names in the diagram are illustrative. Spring Kafka generates retry topic names based on the base topic, suffix, and configured numbering/naming strategy. Check the actual topic names created rather than relying on a specific default suffix.

A retry topic does not create wait times purely through Kafka retention. Spring Kafka attaches backoff metadata to the record and coordinates the retry topic listener so the record is processed only when its retry time arrives. Before it is due, the corresponding partition can be paused; the consumer continues to be managed by the listener container mechanism.

## 3. How Non-Blocking Retry Differs from Blocking Retry

| Criterion | Blocking retry | Non-blocking retry |
| --- | --- | --- |
| Retry mechanism | Retries at the current consumer/listener | Publishes record to a retry topic |
| Consumer thread | Waits for backoff and retry | Does not hold the main thread for the entire delay duration |
| Subsequent records | May be blocked on the retrying partition | Can continue being processed from the main topic |
| Ordering | Keeps partition flow more predictable when processed sequentially | May reorder failed records relative to subsequent records |
| Infrastructure | Primarily needs the main topic and an error handler | Requires additional retry topics, listeners, and a DLT |
| Best suited for | Short retries requiring strict ordering | Long delays, isolating failing records |

Neither approach is always better. If event ordering per aggregate is a strict requirement, blocking retry may be more appropriate. If events are independent and throughput is prioritized, retryable topics can reduce the impact of a failing record.

## 4. Enabling Retry Topic Infrastructure

With pure Java configuration, enable the retry topic mechanism using `@EnableKafkaRetryTopic`. This annotation activates Spring Kafka's retry topic infrastructure and includes the necessary listener support.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafkaRetryTopic;

@Configuration
@EnableKafkaRetryTopic
public class KafkaRetryConfiguration {
}
```

In Spring Boot, still ensure that retry topic infrastructure is enabled according to the configuration of the Spring Kafka version in use. Do not register duplicate enable/retry infrastructure configurations if the application already has an equivalent setup.

Spring Kafka has supported non-blocking retry since the 2.7 line. Verify that your Spring Kafka version is compatible with the project's Spring Boot and Kafka client versions before using newer annotations or attributes.

## 5. Declaring @RetryableTopic

The most concise approach is to place `@RetryableTopic` alongside `@KafkaListener` on the main handler method:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final OrderService orderService;

    public OrderCreatedListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(
                    delay = 1_000,
                    multiplier = 2.0,
                    maxDelay = 10_000),
            retryTopicSuffix = "-retry",
            dltTopicSuffix = "-dlt")
    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-projection")
    public void onMessage(OrderCreatedEvent event) {
        orderService.process(event);
    }
}
```

In this example, `attempts = "4"` represents the maximum total number of deliveries, including the initial attempt on the main topic. Therefore, the record has up to three additional attempts on the retry path. The backoff grows by a factor of 2: the delays are 1 second, 2 seconds, and 4 seconds, capped at a maximum of 10 seconds if further attempts were needed.

`retryTopicSuffix` and `dltTopicSuffix` define topic naming conventions. Specific retry topics are created by the framework based on the suffixing strategy and backoff configuration. The annotation supports many additional attributes, but it is best to start with clear settings for attempt count, backoff, suffixes, and DLT policy.

## 6. Understanding attempts and backoff

`attempts` represents the total number of times the listener can receive a record across the entire flow, including the first processing attempt. For example:

| `attempts` | Initial attempt on main topic | Additional retry attempts |
| --- | ---: | ---: |
| `1` | 1 | 0 |
| `2` | 1 | 1 |
| `3` | 1 | 2 |
| `4` | 1 | 3 |

Backoff determines the wait time before the next attempt. For example:

```java
@Backoff(delay = 2_000)
```

Retries after roughly 2 seconds for each attempt. With exponential backoff:

```java
@Backoff(delay = 1_000, multiplier = 2.0, maxDelay = 30_000)
```

The wait interval grows exponentially and is capped at 30 seconds. This reduces pressure on a recovering downstream service instead of repeatedly resending requests at a short fixed interval.

Backoff is not a millisecond-exact execution guarantee. Consumer lag, scheduling, rebalancing, broker load, and record processing time can cause actual execution to occur later.

## 7. How Retry Topics Are Selected

With multiple distinct backoff intervals, Spring Kafka creates corresponding retry topics according to the suffixing strategy. A logical example:

| Route | Role |
| --- | --- |
| `orders.created` | Initial delivery |
| `orders.created-retry-0` | Retry after a short delay |
| `orders.created-retry-1` | Retry after a longer delay |
| `orders.created-dlt` | Receives records after exhausting attempts |

The names above are illustrative. Depending on `TopicSuffixingStrategy` and the configuration for reusing topics with the same delay, the framework may use suffixes based on index or delay duration and may reuse a retry topic for multiple attempts sharing the same delay.

When configuring multiple retry topics, avoid creating too many topics for a single listener without a clear need. Every topic adds partitions, metadata, consumer assignments, and operational overhead.

## 8. Exception Classification: Which Errors Are Retried?

Not every exception should enter the retry path. Transient failures such as timeouts or connection errors can recover on their own. Data errors such as invalid payloads usually do not change after retrying.

`@RetryableTopic` supports specifying which exceptions to include or exclude:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        include = {
                java.util.concurrent.TimeoutException.class,
                org.springframework.dao.TransientDataAccessException.class
        },
        exclude = {
                IllegalArgumentException.class,
                UnsupportedOperationException.class
        })
@KafkaListener(topics = "orders.created", groupId = "orders-projection")
public void onMessage(OrderCreatedEvent event) {
    orderService.process(event);
}
```

Check the cause chain if a service wraps the root exception inside another exception. Spring Kafka provides a `traversingCauses` option to inspect nested causes during classification. If neither `include` nor `exclude` is configured, the framework applies default classification; certain deserialization/conversion errors and unrecoverable exceptions are treated as fatal and can go straight to the DLT.

Practical guidelines:

- Retry transient infrastructure errors: timeouts, interrupted connections, and recoverable rate limits.
- Do not waste retries on data errors: invalid schema, missing required fields, or unconvertible values.
- Do not retry permanent logic errors: invalid business states requiring intervention or data repair.
- Cap the number of attempts and total duration to avoid keeping records in the system for too long.

## 9. Handling DLT Records with @DltHandler

When attempts are exhausted, the record is published to the DLT. You can declare `@DltHandler` in the same bean as the listener to handle that record:

```java
import org.springframework.kafka.annotation.DltHandler;

@DltHandler
public void onDlt(OrderCreatedEvent event) {
    // Log the error, store investigation details, or raise an alert.
    deadLetterService.recordFailure(event);
}
```

`@DltHandler` is the listener that handles messages on the DLT corresponding to the retryable endpoint. If no custom handler is declared, Spring Kafka uses a default DLT handler that logs the record. In production, establish a clear policy: persist the failed record, store exception metadata, send alerts, create tickets, or route it into a replay workflow.

Do not simply log and forget the DLT. Monitor the record count, age of the oldest record, growth rate, and processing status. A DLT is a queue that must be managed as part of operational procedures.

## 10. Creating Retry Topics and the DLT

Spring Kafka can automatically create retry topics and the DLT via Kafka Admin when `autoCreateTopics` is enabled. You can specify the partition count and replication factor for the created topics:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        autoCreateTopics = "true",
        numPartitions = "6",
        replicationFactor = "3")
@KafkaListener(topics = "orders.created", groupId = "orders-projection")
public void onMessage(OrderCreatedEvent event) {
    orderService.process(event);
}
```

This example requests that retry/DLT topics be created with six partitions and a replication factor of three. The cluster must have enough brokers and suitable configuration to satisfy that replication factor.

In production, many operations teams choose to provision topics via IaC or cluster governance workflows and set `autoCreateTopics = "false"`. In that case, all retry topics and the DLT must be pre-created with the exact names, partition count, replication factor, retention, cleanup policy, and ACLs. If using a partition resolver that preserves the original record's partition, the retry topic/DLT must have matching partitions.

Do not rely solely on broker auto topic creation when the system requires control over replication factor, retention, or access permissions. Auto-created topics may use default settings unsuitable for production.

## 11. Partitions and Keys on Retry Topics

Spring Kafka attempts to preserve partition affinity when forwarding records to retry topics so that routing remains predictable. Therefore, retry topics must have a partition count compatible with the original topic. If the original topic has six partitions while the retry topic has only one partition, forwarding by partition index can fail.

The record key is normally preserved when publishing to a retry topic, helping keep aggregate identity intact. However, this does not guarantee ordering across the main topic and retry topics: later records may already have been processed before the failed record returns.

When creating topics manually, verify:

- Sufficient partition count to map partitions from the original topic.
- Appropriate replication factor and min ISR for the desired durability.
- Retention long enough to cover backoff intervals and consumer outage durations.
- ACLs allowing producers to publish to retry/DLT topics and consumers to read from them.
- Topic names matching the suffixing strategy used by the application.

## 12. Ordering and Idempotency

Non-blocking retry allows subsequent records to continue processing while a failed record waits for retry. Consequently, processing order can change:

```text
Write order in main topic:
  E1 -> E2 -> E3

Possible processing order:
  E1 -> E2 (failed, sent to retry topic) -> E3 -> E2 (retry succeeded)
```

If E2 and E3 both update the same aggregate, processing E3 before E2 can produce an incorrect state. Evaluate business ordering requirements before choosing non-blocking retry.

Risk mitigation measures:

- Use an event version or sequence number per aggregate to detect out-of-order events.
- Design idempotent consumers so duplicates do not cause repeated side effects.
- Only use non-blocking retry for events that can be processed independently or tolerate delayed processing.
- If strict per-partition ordering is required, consider blocking retry or redesigning the event flow.
- Use an inbox/unique event ID when database write side effects could be re-executed.

Non-blocking retry is not an exactly-once mechanism. Publishing a record to a retry topic and committing the original offset can still have a failure window; consumers must tolerate duplicates according to the stream's actual delivery semantics.

## 13. Limitations: Batch Listeners and Kafka Transactions

Non-blocking retry has several important architectural limitations:

**Batch listeners are not supported.** The retryable topic infrastructure is designed around processing and forwarding individual records. If a listener receives `List<ConsumerRecord<...>>` in batch mode, `@RetryableTopic` cannot be applied directly as with a record listener.

**Cannot be combined with container transactions.** Non-blocking retry topics do not support listener containers running Kafka transactions for EOS read-process-write. When using container transactions, choose transaction-compatible retry/rollback mechanisms such as blocking retry and `DefaultAfterRollbackProcessor`.

**Does not preserve main topic ordering.** A failed record may be processed after subsequent records.

**Adds operational infrastructure.** Retry topics and the DLT must be provisioned, monitored, protected with ACLs, and have their retention managed.

If system requirements include batch processing, container transactions, or strict ordering, reconsider the architecture before adopting retryable topics.

## 14. Configuration with RetryTopicConfigurationBuilder

Beyond annotations, retry topics can be configured programmatically using `RetryTopicConfigurationBuilder`. This is useful when applying a single policy across multiple topics or separating configuration from listeners:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.retrytopic.RetryTopicConfiguration;
import org.springframework.kafka.retrytopic.RetryTopicConfigurationBuilder;

@Configuration
public class RetryTopicConfigurationSetup {

    @Bean
    public RetryTopicConfiguration ordersRetryConfiguration(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {

        return RetryTopicConfigurationBuilder.newInstance()
                .exponentialBackoff(1_000, 2.0, 10_000)
                .maxAttempts(4)
                .retryTopicSuffix("-retry")
                .dltSuffix("-dlt")
                .create(kafkaTemplate);
    }
}
```

The builder allows configuring backoff, attempt counts, suffixes, and topic scope. When using the builder, check the methods available in your project's exact Spring Kafka version; the API may expand across releases. Avoid configuring the same listener/topic with overlapping annotation and builder policies without clearly establishing precedence and scope.

## 15. Using the DLT as an Operational Workflow

A DLT is not just a dumping ground for failed messages. Design a handling lifecycle:

1. Record the original topic, partition, offset, and event ID.
2. Store the exception type, message, and delivery attempt as controlled metadata.
3. Alert when DLT volume spikes abnormally or records remain unaddressed for too long.
4. Categorize data errors, code bugs, and infrastructure failures.
5. Fix the root cause before replaying.
6. Replay to the main topic or a dedicated reprocessing topic with idempotency to avoid duplicate side effects.
7. Maintain an audit log of who executed the replay and its outcome if it is a sensitive operational procedure.

Do not bulk-replay DLT messages back into the main topic before fixing the underlying bug. Doing so can trigger error loops and cause the backlog to grow even faster.

## 16. Testing the Retryable Topic Pattern

Integration tests should verify the entire topology rather than only unit-testing the listener method.

A basic test scenario:

1. Start a test broker and create the `orders.created` topic.
2. Configure the listener with `@RetryableTopic`, a small number of attempts, and short backoff.
3. Send an event where the service intentionally fails on the first two attempts and then succeeds.
4. Verify that the event traverses the retry path and is eventually processed successfully.
5. Send an event that always fails and verify it appears on the DLT after attempts are exhausted.
6. Verify that `@DltHandler` receives the expected payload and error metadata.

Additional cases worth testing:

- Exceptions in `include` are retried.
- Exceptions in `exclude` bypass the normal retry path.
- Multi-level backoff produces the configured retry path.
- Retry/DLT topics have partitions matching the original topic.
- Record keys and custom headers are preserved as expected.
- Subsequent records are processed while an earlier record awaits retry, confirming ordering behavior.
- The DLT handler fails and the DLT error policy is applied.
- Consumer restarts/rebalances occur while a record is awaiting retry.

Use `CountDownLatch`, `BlockingQueue`, or Awaitility to await events and DLT arrivals with timeouts. Do not use a short `Thread.sleep` and conclude that retry topics are broken; total processing time includes polling, backoff, scheduling, and consumer assignment.

## 17. Monitoring and Operations

When running non-blocking retry, monitor the main topic, retry topics, and DLT together:

| Metric | Meaning |
| --- | --- |
| Main consumer lag | Whether the main flow is keeping up with incoming records |
| Retry topic lag | Whether retried records are being processed on schedule |
| DLT record count | Number of failures that have exhausted all attempts |
| Age of oldest retry record | How long the oldest pending retry record has been waiting |
| Retry rate by exception | Which error groups are generating the most retries |
| DLT publish failure | Whether forwarding failed records to the DLT is failing |
| Processing latency | Actual latency from receiving a record to completing processing |
| Rebalance count | Whether the consumer group is rebalancing frequently |

Low lag on the main topic does not mean all events have finished processing: records may still be sitting in retry topics. Aggregate the state across the entire topology to measure end-to-end processing time.

## 18. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Records are not retried | Exception is classified as non-retryable or retry infrastructure is not enabled | Check `include`/`exclude`, fatal exceptions, and `@EnableKafkaRetryTopic` |
| Retry topics are not created | Missing Admin permissions, `autoCreateTopics=false`, or misconfigured topic settings | Check `AdminClient`/ACLs and provision topics manually |
| Failure publishing to retry topic | Retry topic lacks matching partitions or serializer is incompatible | Align partition counts and producer configuration |
| Records land in DLT too early | `attempts` includes the initial delivery or exception is treated as fatal | Verify `attempts` count and exception classification |
| Events processed out of order | Main topic continues while older records await retry | Use blocking retry or implement ordering/versioning |
| Retry delay longer than configured | Consumer lag, pauses, rebalances, or broker load | Monitor retry topic lag and actual execution timestamps |
| DLT grows continuously | Data corruption or unresolved downstream outage | Classify errors, alert, and execute replay procedures |
| Batch listener cannot use retryable topic | Non-blocking retry does not support batch listeners | Switch to a record listener or use blocking retry |
| Transactional listener incompatible | Non-blocking retry cannot be combined with container transactions | Use transaction-based retry/rollback |

## 19. Conclusion

Spring Kafka's retryable topic pattern implements non-blocking retry by forwarding failed records from the main topic to retry topics scheduled at appropriate processing times. If retries continue to fail, records progress through retry stages and can ultimately be routed to a DLT. `@RetryableTopic` lets you declare attempts, backoff, exception classification, and naming conventions; `@DltHandler` processes records that have exhausted retries.

This pattern allows the main flow to continue processing other records while failed ones wait for retry, at the cost of additional topics, consumers, and operational requirements. In return, ordering may change, and batch listeners as well as container transactions are not supported. Choose non-blocking retry when business logic tolerates delayed or out-of-order processing, apply idempotency to handle redelivery, manage partition counts, retention, and ACLs for retry topics, and treat the DLT as a monitored operational workflow.

## References

- [Spring for Apache Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
- [Spring for Apache Kafka — @RetryableTopic API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/annotation/RetryableTopic.html)
- [Spring for Apache Kafka — @DltHandler API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/annotation/DltHandler.html)
- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)

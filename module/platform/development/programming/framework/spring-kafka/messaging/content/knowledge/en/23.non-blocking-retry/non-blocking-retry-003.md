# Backoff Between Retry Topics

Non-blocking retry allows an application to forward a failing record to a retry topic for reprocessing after a wait period. The main topic consumer can continue receiving other records while the failed record goes through a separate retry flow. The wait interval between attempts is called backoff. Choosing an appropriate backoff gives dependent services time to recover, reduces pressure during overload, and prevents aggressive retry bursts.

In Spring Kafka, you can declare a backoff schedule for retry topics using `@RetryableTopic` and `@Backoff`. This schedule can be fixed or exponentially increasing. Understanding the attempt count, delay intervals, and how retry topics are created helps predict reprocessing times and impacts on event ordering.

## 1. How Backoff Works in Non-Blocking Retry

With non-blocking retry, when a listener throws a retryable exception, Spring Kafka forwards the record to the corresponding retry topic. A retry listener consumes the record from that topic and processes it only when the backoff interval for that attempt is due. If the listener continues to fail, the record advances to the next retry step. Once attempts are exhausted, the record goes to a dead-letter topic (DLT) if the flow is configured with a DLT.

General flow:

```text
orders
   |
   | listener fails
   v
orders-retry (attempt 1, wait per backoff)
   |
   | retry listener still fails
   v
orders-retry (next attempt)
   |
   | attempts exhausted
   v
orders-dlt
```

Actual topic names depend on topic suffixes, the suffixing strategy, and application configuration. Spring Kafka creates or uses retry topics according to the declared backoff schedule. A retry topic may represent a single delay interval or be reused depending on configuration; do not infer topic names solely from the attempt count.

Backoff is the wait time before another attempt, not the listener execution time. Total elapsed time also depends on per-attempt processing duration, publish/consume overhead, broker load, and the retry listener's scheduling loop.

## 2. Fixed Backoff

Fixed backoff uses the same wait interval between retries. For example, setting `delay = 2_000` gives each transition to the next retry a target delay of two seconds.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    private final OrderService orderService;

    OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(delay = 2_000L),
            dltTopicSuffix = "-dlt")
    @KafkaListener(topics = "${app.kafka.orders-topic}")
    public void onOrder(OrderCreated event) {
        orderService.handle(event);
    }
}
```

`attempts = "4"` is the total number of processing attempts, including the initial attempt on the main topic. Thus this example allows at most three retries. If all four attempts fail, the record is forwarded to the DLT as configured. With a two-second fixed backoff, the target wait times before the retry attempts are two seconds, two seconds, and two seconds.

Fixed backoff works well when the dependent service typically recovers quickly and retry load is steady. However, if a system is overloaded, many records retrying after the exact same interval can create a new spike of load.

## 3. Exponential Backoff

Exponential backoff increases the wait interval after each failure. Basic formula:

\[
d_n = \min(d_0 \times m^{n-1}, d_{max})
\]

Where:

- \(d_0\) is the initial delay (`delay`).
- \(m\) is the growth factor (`multiplier`), usually greater than 1.
- \(d_{max}\) is the maximum cap (`maxDelay`).
- \(n\) is the retry attempt index, starting from 1.

For example, configuring `delay = 1 second`, `multiplier = 2`, and `maxDelay = 6 seconds` produces a wait schedule of 1, 2, 4, 6, 6 seconds for consecutive retries. The upper cap prevents wait times from growing indefinitely.

```java
@RetryableTopic(
        attempts = "6",
        backoff = @Backoff(
                delay = 1_000L,
                multiplier = 2.0,
                maxDelay = 6_000L),
        dltTopicSuffix = "-dlt")
@KafkaListener(topics = "${app.kafka.orders-topic}")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

With `attempts = "6"`, the listener has one initial processing attempt and up to five retries. The target wait schedule before each attempt is:

| Processing attempt | Record destination | Backoff before this attempt |
| --- | --- | ---: |
| 1 | Main topic | 0 seconds |
| 2 | Retry topic 1 | 1 second |
| 3 | Retry topic 2 | 2 seconds |
| 4 | Retry topic 3 | 4 seconds |
| 5 | Retry topic 4 | 6 seconds |
| 6 | Retry topic 5 | 6 seconds |
| After attempt 6 fails | DLT | No more retries |

The total target wait time before the sixth processing attempt is 19 seconds, excluding processing time and record transport latency. This table helps estimate recovery windows and set limits aligned with business requirements.

## 4. Reading Backoff Attributes Correctly

Commonly used attributes in `@Backoff`:

| Attribute | Meaning | How to choose |
| --- | --- | --- |
| `delay` | Initial delay or fixed wait interval, in milliseconds | Set based on the minimum time needed for the dependent service to recover |
| `multiplier` | Factor by which the wait interval multiplies after each retry | Use a value greater than 1 to increase gradually; 1 keeps the interval constant |
| `maxDelay` | Upper limit on wait time when using exponential backoff | Cap it so retry duration does not exceed SLAs or processing deadlines |
| `random` | Enables random jitter for exponential backoff schedules as supported by Spring Retry | Consider enabling to prevent many records from retrying simultaneously |

`@Backoff` is a Spring Retry annotation used by Spring Kafka when declaring retry topic backoff. Values must match your project's dependency version. If only `delay` is declared, the schedule is fixed. When using `multiplier`, explicitly set `maxDelay` so the upper bound is predictable.

## 5. Attempts and Retry Count

`attempts` represents the total number of times the listener is invoked, including the initial attempt on the main topic. The maximum number of retries is:

\[
\text{retries} = \text{attempts} - 1
\]

Examples:

| `attempts` | Initial attempt | Maximum retries |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 3 | 1 | 2 |
| 4 | 1 | 3 |
| 6 | 1 | 5 |

Do not set `attempts` to the desired number of retries while forgetting the first processing attempt. If you need one initial attempt and four retries, set `attempts = "5"`.

Not every exception should go through the backoff schedule. You can use `include` to specify retryable exception groups or `exclude` to rule out unrecoverable errors, depending on policy and Spring Kafka version. For example, partner service timeout errors can be retried, whereas deterministic data validation errors should go directly to the DLT.

## 6. Retry Topics and Delay-Based Routing

Spring Kafka uses the backoff schedule to determine which retry topic a record will be forwarded to. With an exponential schedule, each distinct delay interval may require its own retry topic. With a fixed schedule, the framework can reuse a retry topic according to the configured strategy.

Several configuration options affect the topology:

- `retryTopicSuffix` and `dltTopicSuffix`: suffixes for retry topic and DLT names.
- `topicSuffixingStrategy`: how each retry topic suffix is generated, such as by index or by delay duration.
- `sameIntervalTopicReuseStrategy`: how topics are reused when multiple retries share the same delay, if supported by your Spring Kafka version.
- `autoCreateTopics` or application-managed topic configuration: determines how topics and partition/replica counts are created.

Inspect the actual topology created in a real environment. Do not assume a single topic handles all retries or manually invent topic names from an example without checking the active suffixing strategy.

Retry topics need appropriate partition counts, replication factors, and ACLs. Partition counts affect parallel processing capacity; retry listener concurrency cannot exceed the number of assignable partitions. Monitor lag on each retry topic to detect backlogs in a particular delay tier.

## 7. Backoff and Event Processing Order

Non-blocking retry lets the main topic continue processing records after a failed record is forwarded to a retry topic. Consequently, overall processing order can change. For instance, if an `OrderCreated` event fails and moves to a retry topic, a subsequent `OrderCancelled` event may be processed before `OrderCreated` succeeds on retry.

This is especially important when events sharing the same key or aggregate depend on order. If business logic requires strict ordering, consider blocking retry with `DefaultErrorHandler`, implementing sequence/version checks in the consumer, or partitioning/isolating event flows appropriately. Do not adopt non-blocking retry solely for flexible backoff while ignoring ordering requirements.

## 8. Choosing Backoff Based on Error Characteristics

| Scenario | Suitable backoff | Reason |
| --- | --- | --- |
| Dependent service errors typically recover quickly | Fixed backoff | Simple, predictable schedule |
| Service may experience prolonged overload | Exponential backoff with `maxDelay` | Gradually increases wait time, easing retry pressure |
| Many records may fail simultaneously | Exponential backoff with random/jitter if suitable | Reduces thundering-herd retries |
| Events have short validity windows | Short backoff, few attempts | Avoids retrying after results are no longer valid |
| Events require strict in-partition ordering | Consider blocking retry or custom ordering design | Retry topics allow later records to overtake failed ones |

A backoff that is too short can trigger a retry storm. A backoff that is too long increases end-to-end completion latency and builds up backlogs in retry topics. Choose attempt counts and wait schedules based on SLAs, actual dependency recovery times, and event criticality.

## 9. Observability and Operations

To evaluate whether a backoff schedule is effective, monitor:

- Number of records routed into each retry topic and the DLT.
- Consumer lag and age of the oldest record on each retry topic.
- Retry success rate at each attempt stage.
- Total elapsed time from initial receipt to successful processing or DLT arrival.
- Failures publishing to retry topics, deserialization errors, and processing errors in retry listeners.
- Number of records replayed from the DLT and replay success rate.

When changing `attempts`, `delay`, `multiplier`, or `maxDelay`, the retry topic topology may change. Provision corresponding topics, verify permissions, and plan how to drain or handle records still residing in old topics before changing configuration in production.

## 10. Testing the Backoff Schedule

Tests should verify listener invocation counts, topic transition order, and scheduled wait behavior, without relying on millisecond-exact timing comparisons. You can use embedded Kafka or a test broker combined with a spy/mock service to count processing attempts.

1. Send a record that causes the listener to fail on initial attempts and succeed later; verify the record moves through retry topics in the expected order.
2. With fixed backoff, verify intervals between attempts approximate the configured `delay` within test environment tolerances.
3. With exponential backoff, verify wait intervals grow by `multiplier` and do not exceed `maxDelay`.
4. Verify `attempts` includes the initial attempt and actual retries equal `attempts - 1`.
5. Force the listener to fail on all attempts; verify the record ultimately lands on the DLT.
6. Send two events with the same key where the first is retried; verify the application handles your chosen ordering requirements properly.

## 11. Implementation Checklist

- [ ] `@RetryableTopic` declares `attempts` as the total number of processing attempts, including the initial attempt.
- [ ] `@Backoff` specifies an appropriate `delay`; if using exponential backoff, `multiplier` and `maxDelay` are explicitly set.
- [ ] Decided whether to enable random/jitter to prevent synchronized retry bursts.
- [ ] Retryable and non-retryable exceptions are classified based on business causes.
- [ ] Retry topics and DLT have appropriate names, partitions, replication, and ACLs.
- [ ] Evaluated the impact of retry topics on same-key/same-partition event ordering.
- [ ] Metrics exist for lag, record age, retry success rate, and DLT record count.
- [ ] Tested the backoff schedule, attempt limits, DLT routing, and continuous retry failure scenarios.

Backoff between retry topics is a mechanism for pacing retry attempts. A fixed schedule suits short-lived, predictable errors; exponential backoff suits situations where systems need progressively more time to recover after repeated failures. Combining wait schedules with exception classification, DLT handling, ordering requirements, and monitoring keeps non-blocking retry under control.

# slidingWindowSize and the Amount of Data Stored

In Spring Cloud CircuitBreaker using Resilience4j, the Circuit Breaker needs to observe recent call outcomes to decide whether to keep sending requests to a dependency or transition to the OPEN state. The *sliding window* defines the scope of data used for that decision. The `slidingWindowSize` property configures the window size, though the meaning of this number depends on the chosen window type.

The key point to understand clearly is that the sliding window stores measurements used to calculate the failure rate and slow call rate. It does not store entire requests, responses, or business payloads. Therefore, the window size determines the amount of statistical history retained, not the number of HTTP bytes the application might store.

## 1. What is a sliding window used for?

Each time a call passes through the Circuit Breaker, Resilience4j records the outcome according to that Circuit Breaker's configuration. An outcome can be a success, a failure, or a slow call. From the measurements in the current window, the Circuit Breaker computes:

- **Failure rate**: the percentage of calls recorded as failed.
- **Slow call rate**: the percentage of calls whose execution time exceeds the slow call threshold.
- **Number of recorded calls** in the window, used as the basis to determine whether there is enough data for evaluation.

The sliding window enables decisions based on recent health. For example, a dependency may have failed many times previously but has since recovered. If the Circuit Breaker continued to include errors from a long time ago, it could keep a negative assessment for too long. As the window slides, older measurements leave the statistical scope one by one and new measurements are added.

You can visualize the process as follows:

~~~mermaid
flowchart LR
    A[Call to dependency] --> B[Record outcome and duration]
    B --> C[Update sliding window]
    C --> D{Reached minimumNumberOfCalls?}
    D -- No --> E[Continue collecting data]
    D -- Yes --> F[Compute failure rate and slow call rate]
    F --> G{Any threshold exceeded?}
    G -- No --> H[Stay CLOSED]
    G -- Yes --> I[Transition to OPEN]
~~~

The window itself does not decide whether a call is retried. It provides statistics for the Circuit Breaker to evaluate its state. Retry is a separate mechanism and must be configured according to the application's transient error policy.

## 2. Two Window Types and the Meaning of slidingWindowSize

Resilience4j supports two main window types:

| Window type | Meaning of `slidingWindowSize` | Retained history scope |
|---|---|---|
| `COUNT_BASED` | Number of most recent calls | Up to N recently recorded calls |
| `TIME_BASED` | Number of most recent seconds | Measurements within the last N seconds |

### COUNT_BASED: count-based sliding window

With `COUNT_BASED`, `slidingWindowSize: 100` means the Circuit Breaker aggregates up to the 100 most recent calls. Each newly recorded call advances the window. Once the window holds 100 measurements, the oldest measurement is evicted from the scope and the new measurement is added.

For example, a window of size 5:

| Point in time | Five measurements currently retained |
|---|---|
| After call 5 | 1, 2, 3, 4, 5 |
| After call 6 | 2, 3, 4, 5, 6 |
| After call 7 | 3, 4, 5, 6, 7 |
| After call 8 | 4, 5, 6, 7, 8 |

When new calls arrive, the oldest results leave the window in order. If traffic spikes sharply, 100 calls might represent only a few seconds. If traffic is very low, 100 calls could span several minutes or hours. Hence, this type reflects the count of recent requests and does not guarantee a fixed time interval.

Configuration example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
~~~

In this example, the Circuit Breaker keeps up to the 100 most recent call measurements. Only when at least 20 calls have been recorded in the window does it start evaluating the failure rate and slow call rate. A threshold of 50 means a corresponding rate of 50% or higher can cause the Circuit Breaker to open the circuit.

### TIME_BASED: time-based sliding window

With `TIME_BASED`, `slidingWindowSize: 10` means the Circuit Breaker aggregates measurements over the last 10 seconds. The size here is in seconds, not number of requests.

Resilience4j divides the time window into per-second buckets. Each bucket aggregates the measurements produced during that second. If 500 calls occur in one second, the results are accumulated into that bucket's aggregates; the Circuit Breaker does not need to allocate a separate bucket for each request.

For example, a 5-second time window:

| Evaluation time | Time buckets included |
|---|---|
| 12:00:05 | 12:00:01 to 12:00:05 |
| 12:00:06 | 12:00:02 to 12:00:06 |
| 12:00:07 | 12:00:03 to 12:00:07 |

As time advances, the oldest bucket leaves the window and the bucket for the new second is used. The number of requests in each second can vary, yet the number of buckets in the window remains bounded by the configured number of seconds.

Configuration example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
~~~

In this example, the Circuit Breaker examines data over the last 10 seconds. It only evaluates rates when a minimum of 20 calls have been recorded within that window. If only 8 calls occurred in 10 seconds, even if all 8 failed, the minimum sample condition is not yet met.

## 3. Does slidingWindowSize store entire requests?

No. Resilience4j's sliding window is designed for efficient statistics collection, not for storing full transaction histories.

The measurements are used to aggregate information such as:

- Number of recorded calls.
- Number of failed calls.
- Number of slow calls.
- Total execution duration used for statistics.

Depending on the window type, measurements are stored as individual measurement entries or aggregated buckets. The Circuit Breaker does not need to store full request contents, response bodies, HTTP headers, business data, or full records of each transaction to compute these rates. To retain information for investigating specific requests, the application should use logging, tracing, or an appropriate event storage system.

Differences in storage between the two window types:

| Characteristic | COUNT_BASED | TIME_BASED |
|---|---|---|
| Size unit | One call | One second |
| Conceptual structure | Ring buffer of N call measurements | Ring buffer of N buckets, each aggregating one second |
| When more traffic arrives | Each new call replaces the oldest measurement when the window is full | Calls within the same second are accumulated into the time bucket |
| Factor determining window structure capacity | Size of N calls | Size of N seconds |
| Does it store request/response bodies? | No | No |

Both types use a ring buffer structure and aggregated metrics to avoid scanning the entire history every time a snapshot is needed. The cost of updates and taking snapshots is designed to be constant with respect to the number of measurements in the window; the structure's capacity scales with the configured window size.

This does not mean the entire application always uses the same amount of memory. Each Circuit Breaker instance maintains its own state and window. If the application creates many instances with distinct names, total memory dedicated to the windows also increases with the number of instances.

## 4. Distinguishing slidingWindowSize and minimumNumberOfCalls

These two properties are often confused because both relate to measurement counts.

- `slidingWindowSize` defines the size of the window: number of calls for `COUNT_BASED`, or number of seconds for `TIME_BASED`.
- `minimumNumberOfCalls` defines the minimum number of calls needed in the window before the Circuit Breaker computes the failure rate and slow call rate to evaluate thresholds.

Example with `COUNT_BASED`:

~~~yaml
slidingWindowType: COUNT_BASED
slidingWindowSize: 50
minimumNumberOfCalls: 20
failureRateThreshold: 50
~~~

Explanation:

1. The window can hold outcomes of up to the 50 most recent calls.
2. After 10 calls, the Circuit Breaker does not yet have the 20 samples required to evaluate rates.
3. Once 20 calls are recorded, the Circuit Breaker begins calculating rates over the currently available samples.
4. Once the window is full, each new call causes the oldest measurement to leave the window, and metrics are calculated over the 50 most recent calls.

If 10 out of the first 20 calls fail, the failure rate is 50%. With `failureRateThreshold: 50`, the error threshold is reached and the Circuit Breaker can transition to OPEN.

Example with `TIME_BASED`:

~~~yaml
slidingWindowType: TIME_BASED
slidingWindowSize: 10
minimumNumberOfCalls: 20
failureRateThreshold: 50
~~~

Explanation:

1. The statistical window covers the last 10 seconds.
2. `minimumNumberOfCalls: 20` requires at least 20 calls within that period.
3. If only 8 calls occur in 10 seconds, the Circuit Breaker does not yet evaluate rates.
4. If there are 40 calls, rates are computed over the calls recorded in the 10-second window.

With `COUNT_BASED`, the minimum sample count should fit within the maximum number of calls the window can hold. With `TIME_BASED`, the minimum number of calls is an independent threshold from the number of seconds in the window; a 10-second window can easily require a minimum of 100 calls if expected traffic is high enough.

## 5. What data counts as success, failure, or slow call?

The window is only useful when you understand how the Circuit Breaker classifies outcomes. Resilience4j provides configuration to specify which exceptions are recorded as failures, which are ignored, and supports predicates to decide based on error type.

A successful call increments the successful call count. An exception configured to be recorded as a failure increments the failed call count. An exception configured to be ignored is not counted as either a successful or failed call in the Circuit Breaker's statistics.

A slow call is determined by `slowCallDurationThreshold`. A call can succeed yet still be counted as slow if its execution time exceeds the threshold. A failed call can also simultaneously be a slow call if it runs longer than the duration threshold.

General formulas:

\[
\text{Failure rate} =
\frac{\text{Number of failed calls}}{\text{Number of recorded calls}}
\times 100\%
\]

\[
\text{Slow call rate} =
\frac{\text{Number of slow calls}}{\text{Number of recorded calls}}
\times 100\%
\]

The denominator is the number of recorded calls in the current window. Ignored exceptions are not treated as successful samples to dilute the failure rate. Therefore, configuring `recordExceptions`, `ignoreExceptions`, or related predicates can directly influence the decision to open the circuit.

For example, an inventory service returns a 404 error because a product code does not exist. If this is a normal business result, the application should consider not counting this error as an infrastructure failure of the dependency. Conversely, a connection error or a 503 error may be signals that should be recorded so the Circuit Breaker can assess the service's health.

## 6. Choosing Window Size Based on Traffic and Protection Goals

There is no single `slidingWindowSize` number that fits every dependency. You need to consider traffic volume, traffic volatility, response time, and how quickly the system needs to detect incidents.

### When should you choose COUNT_BASED?

COUNT_BASED is appropriate when you want to evaluate a fixed number of recent requests and traffic may vary over time. For example, the system always wants to examine the 100 most recent calls regardless of whether they occurred within one second or one minute.

A window that is too small can allow a few random errors to swing the rate sharply. A window that is too large dilutes new errors with many older results, causing the Circuit Breaker to react more slowly to newly emerging incidents.

### When should you choose TIME_BASED?

TIME_BASED is appropriate when you want to evaluate dependency health over a fixed time period, such as the last 10 or 60 seconds. This type is useful when comparing error rates in real time, especially when traffic changes significantly across different times.

A window that is too short may react too strongly to a small burst of errors or traffic spikes. A window that is too long may retain the impact of an ended incident longer than desired. You should choose an appropriate `minimumNumberOfCalls` to avoid making decisions from too small a sample.

### Factors to consider

| Factor | Question to answer | Consideration |
|---|---|---|
| Average traffic | How many calls per second does the dependency receive? | Estimate the actual number of samples in the window |
| Traffic spikes | Does traffic surge sharply by hour or by campaign? | TIME_BASED keeps a fixed time span; COUNT_BASED keeps a fixed request count |
| Failure detection speed | How fast does the system need to react? | Short windows are more sensitive but fluctuate more easily |
| Rate stability | Are more samples needed to avoid deciding from a few random errors? | Tune minimumNumberOfCalls |
| Number of Circuit Breaker instances | Does the application create many instances per tenant or per dependency? | Avoid creating unnecessary instances and monitor total resources |
| Memory resources | How many measurements or buckets are retained concurrently? | Choose window size based on actual needs |

## 7. Calculation and Configuration Selection Example

Suppose the order service calls the inventory service an average of 40 times per second. The development team wants the Circuit Breaker to evaluate errors over roughly the last 10 seconds and requires at least 100 calls before making a decision.

The configuration could be:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 100
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

At 40 calls per second, a 10-second window can observe about 400 calls when traffic is steady. This is a traffic estimate, not a fixed quantity the window guarantees to store. If traffic drops, the number of samples in the window decreases; if traffic rises, the number of calls accumulated into the buckets also increases.

Suppose in the last 10 seconds there are 200 recorded calls, of which 120 failed and 80 succeeded. The failure rate is:

\[
\frac{120}{200}\times100\%=60\%
\]

With a threshold of 50%, the failure rate has exceeded the threshold. If the minimum number of samples has been reached, the Circuit Breaker can transition to OPEN.

If using COUNT_BASED with `slidingWindowSize: 400`, the Circuit Breaker evaluates the 400 most recent calls. When traffic is steady at 40 calls per second, this corresponds to about 10 seconds. However, when traffic rises to 100 calls per second, 400 calls cover only about 4 seconds; when traffic drops to 10 calls per second, they can cover about 40 seconds. This is an important difference when choosing a window type.

## 8. Impact on Memory and Number of Circuit Breaker Instances

Window size is part of the memory footprint. With COUNT_BASED, each instance maintains statistical structures for up to N call measurements. Increasing N from 100 to 10,000 noticeably increases the structure allocated for measurements.

With TIME_BASED, the number of buckets depends on the configured number of seconds. For example, a 10-second window has 10 time buckets, and a 60-second window has 60 buckets. Each bucket aggregates the calls within that second, so higher traffic does not increase the number of buckets per request.

However, you should not look at only a single window's size. If an application has 200 Circuit Breaker instances, each instance has its own window. Total cost depends on the number of instances and the structure size of each instance. Avoid dynamically creating instances per request or by values with very high cardinality.

For example, if each tenant gets a dedicated Circuit Breaker and the system has tens of thousands of tenants, total memory can grow sharply even if each individual window is small. Scope instances by dependency or group of operations with similar operational characteristics, and monitor the actual instance count.

You should also distinguish sliding window memory from log, tracing, and metric memory. Logs may contain request payloads if recorded by the application; tracing may store spans and attributes; metrics may grow in cardinality by labels. These components have their own retention policies and are not governed solely by `slidingWindowSize`.

## 9. Observing the Window and Tuning in Operations

Resilience4j can integrate with Micrometer and Spring Boot Actuator to export metrics. Depending on application configuration, these metrics can be scraped by Prometheus and visualized on Grafana.

When monitoring a Circuit Breaker, observe:

- Number of recorded calls and number of calls in the current window.
- Number of failed calls and failure rate.
- Number of slow calls and slow call rate.
- Number of state transitions across CLOSED, OPEN, and HALF_OPEN.
- Number of calls rejected while the Circuit Breaker is OPEN.
- Fallback rate and response latency of the business flow.

When the Circuit Breaker opens too often, check root errors, traffic, timeouts, and exception classification before increasing the window size. If it opens too late, the window may be too large or thresholds unsuitable. If it opens due to a few random errors, review `minimumNumberOfCalls` and dependency stability.

Make deliberate changes to one configuration group at a time and observe the impact under representative load. Do not increase `slidingWindowSize` merely to reduce the displayed failure rate: a larger window can dilute new errors, causing the Circuit Breaker to detect incidents later.

## 10. Common Misconceptions

- **Assuming COUNT_BASED size 100 means 100 seconds**: in reality it is the 100 most recent calls, and the time span covered depends on traffic.
- **Assuming TIME_BASED size 10 means 10 requests**: in reality it is the last 10 seconds, and each second can contain many calls.
- **Assuming the sliding window stores request bodies**: the window holds measurements and aggregated statistics, not full transaction payloads.
- **Equating slidingWindowSize with minimumNumberOfCalls**: one property defines the window size, while the other defines the minimum samples required to evaluate rates.
- **Ignoring the number of instances**: many small windows can still add up to significant memory usage.
- **Looking only at failure rate**: successful but slow calls can still indicate dependency degradation; you must monitor slow call rate as well.
- **Increasing the window without reviewing sensitivity**: a larger window may stabilize decisions, but reacts more slowly to new errors.

## 11. Practical Configuration Process

When configuring a sliding window for a dependency in Spring Cloud CircuitBreaker with Resilience4j, you can follow these steps:

1. Measure actual traffic and latency of the dependency during normal and peak hours.
2. Choose COUNT_BASED if you want to retain a number of recent calls; choose TIME_BASED if you want to retain a recent time interval.
3. Set `slidingWindowSize` in the exact unit of the selected window type.
4. Set `minimumNumberOfCalls` to ensure enough samples before evaluating rates.
5. Define which exceptions are recorded and which are ignored.
6. Set `failureRateThreshold`, `slowCallDurationThreshold`, and `slowCallRateThreshold` according to SLAs and dependency behavior.
7. Monitor metrics, state transitions, and fallbacks under realistic load.
8. Tune the window and thresholds based on observed data, while checking memory impact as the number of instances grows.

By properly understanding `slidingWindowSize`, the development team can control the historical scope the Circuit Breaker uses, estimate memory cost, and choose sensitivity suited to traffic. COUNT_BASED keeps the most recent calls; TIME_BASED keeps per-second statistical buckets. Both enable Resilience4j to evaluate failures and slow calls without storing full request/response data.

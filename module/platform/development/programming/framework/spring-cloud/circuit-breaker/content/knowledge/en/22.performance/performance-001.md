# Statistics Overhead by Window Size and Instance Count

Every Circuit Breaker needs to store its state and call outcome statistics in order to decide when to transition from CLOSED to OPEN or HALF_OPEN. The sliding window size and the number of Circuit Breaker instances therefore directly affect memory usage, statistics update overhead, exported metrics count, and application startup time. Increasing the window or creating more instances can provide more granular analysis, but it also increases operational overhead.

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, you need to choose a window size and instance scope suited to your traffic volume, number of dependencies, and resource budget. Resilience4j uses sliding-window statistical structures to calculate the failure rate and slow call rate; understanding the per-instance cost helps avoid oversized configurations or dynamically creating Circuit Breakers per request.

## 1. Components That Contribute to Circuit Breaker Overhead

A Circuit Breaker instance is not just a state flag. It also manages configuration, current state, sliding window statistics, an event publisher, and metrics integration components if observability is enabled in the application.

Main components:

| Component | Data or Work | Cost Driver |
| --- | --- | --- |
| State machine | CLOSED, OPEN, HALF_OPEN, and state transition timestamps | Number of instances |
| Sliding window | Call count, failure count, slow call count, and aggregated data | Window size and number of instances |
| Event publisher | Emits success, error, rejected, and state transition events | Number of instances, event volume, and listener work |
| Metrics integration | Meters, tags, and observability data for each instance | Number of instances, metric families, and tag combinations |
| Configuration | Thresholds, OPEN duration, window type, and other parameters | Number of configs/instances and configuration layout |

The memory cost of the statistics portion can be approximated as follows:

$$
M_{window} \propto N \times W
$$

Where:

- (N) is the number of Circuit Breaker instances being created.
- (W) is the window size: the number of calls for COUNT_BASED or the number of seconds for TIME_BASED.

This is a complexity model for comparing configurations, not an exact byte-level formula. Actual memory usage also depends on the Resilience4j version, JVM, object layout, metrics, event buffers, and other application components.

## 2. How Resilience4j Stores Sliding Window Statistics

Resilience4j does not need to retain the full request or response objects of every call just to calculate rates. The sliding window uses statistical buckets and aggregations to store the information needed for evaluation.

With COUNT_BASED, the window is sized by the most recent number of calls. When a new outcome arrives, the oldest entry is evicted from the window and the aggregate statistics are updated. With TIME_BASED, the window is divided into time buckets, typically corresponding to each second in the observation interval; data from expired buckets is removed from the aggregation.

Both approaches allow updating and reading statistics with nearly constant per-call cost within the window structure, while the window's memory footprint scales with the configured size. Therefore, increasing the window size increases the number of buckets to manage, but it does not mean Resilience4j must retain the full payload of every request.

This does not mean the overall cost of the application is always O(1). HTTP clients, serialization, logging, event listeners, metrics exporters, and operations inside the dependency call all have their own costs. Describing O(1) here refers specifically to updating and reading the sliding window aggregations per the window design.

## 3. Overhead of COUNT_BASED

With COUNT_BASED, `slidingWindowSize` is the number of most recent call outcomes retained in the window. For example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
~~~

The `inventory` instance tracks up to the 100 most recent outcomes. When the 101st outcome arrives, the oldest outcome leaves the window and is replaced by the new one. The statistics tracker holds the necessary aggregates such as call count, failure count, slow call count, and aggregated duration.

Characteristics of COUNT_BASED:

- Window memory scales with `slidingWindowSize`.
- The actual time span covered by the window varies with traffic volume.
- Under high traffic, 100 calls may represent only a few seconds.
- Under low traffic, the same 100 calls may span many minutes or longer.
- Increasing the window reduces the impact of a few random errors, but keeps older data in the sample set for longer.

COUNT_BASED is appropriate when you want to evaluate based on call count, for example "how many errors occurred in the last 20 calls?". If traffic fluctuates heavily and the requirement is to evaluate over a fixed time span, TIME_BASED may be more suitable.

## 4. Overhead of TIME_BASED

With TIME_BASED, `slidingWindowSize` represents the window length in seconds:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 60
        minimumNumberOfCalls: 50
        failureRateThreshold: 50
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
~~~

The instance tracks outcomes over the last 60 seconds. The window uses time buckets to aggregate outcomes for each interval. When a bucket expires, its metrics are removed from the total.

Characteristics of TIME_BASED:

- Window memory scales with the number of time buckets, i.e., the window length in seconds.
- The number of calls in each bucket depends on traffic; the statistics structure does not need to allocate a new bucket per request.
- The observation time span remains more consistent when traffic changes.
- Under very low traffic, there may not be enough calls to exceed `minimumNumberOfCalls` and evaluate the rates.
- During a traffic spike, the window still covers the same time span, though the number of outcomes recorded within it increases.

TIME_BASED is suitable for requirements such as "failure rate over the last 60 seconds". If you need to evaluate by sample count rather than time, COUNT_BASED is more direct.

## 5. How Window Size Affects Sensitivity and Memory

Window size is a trade-off between detection sensitivity and statistics overhead:

| Window | Impact on Failure Detection | Impact on Resources |
| --- | --- | --- |
| Small | Reacts quickly to recent changes, but fluctuates easily due to small sample size | Fewer buckets, lower window memory overhead |
| Moderate | Balances short-term fluctuations against failure trends | Proportional cost with a moderate number of buckets |
| Large | More stable rates, but new errors can be diluted by older history | More buckets per instance |

For example, a COUNT_BASED window of 10 can open the circuit quickly when 5 out of 10 calls fail. However, a few consecutive failed requests during low traffic can cause the rate to swing sharply. A window of 200 produces a smoother rate, but if a service has just started degrading, many older successful outcomes remain in the window and delay opening the circuit.

Do not increase the window size solely to reduce jitter without checking incident detection speed. The goal is to detect fast enough to protect the application without tripping the circuit due to a handful of isolated errors.

## 6. Role of minimumNumberOfCalls

`minimumNumberOfCalls` specifies the minimum number of outcomes required before the Circuit Breaker calculates the failure rate and slow call rate to decide whether to open the circuit. This parameter does not change the sliding window size, but it affects when the window becomes eligible for evaluation.

For example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
~~~

With this configuration, even if the first 3 calls all fail, the Circuit Breaker does not evaluate the rate to open the circuit because it does not yet have 20 outcomes. Once at least 20 outcomes are recorded, the failure rate is compared against the 50% threshold.

Setting `minimumNumberOfCalls` too low makes decisions overly sensitive to small samples. Setting it too high can force the Circuit Breaker to wait too long before reacting, especially for low-traffic dependencies. It should be chosen alongside the window size and expected traffic.

## 7. Instance Count Multiplies Statistics Overhead

Each Circuit Breaker instance has its own state and sliding window. If an application protects 8 dependencies and each dependency has 3 operation groups, the total number of instances can be:

$$
N = 8 \times 3 = 24
$$

If each instance uses a COUNT_BASED window size of 100, the total number of statistical slots to manage scales with:

$$
24 \times 100 = 2,400
$$

This represents the equivalent number of slots/buckets under the complexity model, not 2,400 request objects or a fixed number of bytes. If you increase the instance count to 240 while keeping the window at 100, the window-related overhead increases roughly 10-fold.

Do not create Circuit Breakers per customer, SKU, request ID, or transaction ID. The following example generates instance names with unbounded cardinality:

~~~java
// Not recommended: each customer can create a separate instance.
String name = "inventory-" + customerId;
CircuitBreaker breaker = registry.circuitBreaker(name);
~~~

Instead, use stable names scoped by dependency or operation group:

~~~java
CircuitBreaker breaker = registry.circuitBreaker("inventory-read");
~~~

If two operations need different thresholds and failure histories, you can use two fixed names such as `inventory-read` and `inventory-reservation`. Each name should correspond to a meaningful operational policy, not a data value derived from requests.

## 8. Shared Configs Do Not Reduce Runtime Instance Count

Resilience4j lets you declare reusable configurations under `configs`, and then have multiple instances reference them via `baseConfig`:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
    instances:
      inventory-read:
        baseConfig: default
      customer-profile-read:
        baseConfig: default
      catalog-read:
        baseConfig: default
~~~

Sharing a config reduces YAML duplication and makes it easier to keep parameters consistent. However, the three keys under `instances` still represent three independent Circuit Breakers. Each instance still maintains its own state, sliding window, and metrics.

Therefore, `baseConfig` simplifies configuration management; it is not a way to merge multiple dependencies into a single sliding window, nor does it eliminate the runtime cost of three instances. To reduce the instance count, review which call scopes truly require independent state.

## 9. Metrics Also Scale with Instance Count

When Micrometer integration is enabled, each Circuit Breaker instance can register meters to track call counts, state, failure rate, and slow call rate. The number of time series depends on the number of instances, the number of meter families, the tags, and how the exporter represents metrics.

This can be approximated as:

$$
S \approx N \times M \times L
$$

Where:

- (S) is the potential number of time series.
- (N) is the number of instances.
- (M) is the number of meter families exported per instance.
- (L) is the number of additional tag combinations per meter.

This is an estimation model, not a fixed formula across all versions. If histograms are enabled, each label set can generate many additional bucket series along with count and sum. As a result, the number of time series can grow faster than the instance count.

Do not add high-cardinality tags such as request ID, customer ID, SKU, or exception messages to metrics. Keep detailed IDs in logs and traces. Instance names should form a finite, stable set of values.

## 10. Event Listener and Logging Overhead

A Circuit Breaker can emit events when calls succeed, fail, are rejected, or when its state changes. Event listeners improve system observability, but listener processing also consumes CPU and can impact latency if heavy work runs directly inside the callback.

For example, listeners should execute quickly:

~~~java
circuitBreaker.getEventPublisher()
        .onStateTransition(event ->
                log.info("Circuit breaker state changed: {}", event))
        .onError(event ->
                log.debug("Circuit breaker call failed: {}", event));
~~~

Avoid making HTTP calls, database queries, or blocking operations inside a listener. If you need to forward events to another system, offload the work to a bounded queue or executor with a policy for handling a full queue.

Do not log every event at the INFO level for a high-traffic dependency unless there is a specific operational need. Use metrics to track aggregated counts and log details only for significant events such as state transitions. Logging every request can increase I/O, storage consumption, and processing overhead.

## 11. Example Comparison of Configurations by Instance Count

Suppose an application has 12 stable dependency operations. Compare the following options:

| Option | Instance Count | Window per Instance | Total Bucket Scale per Model |
| --- | ---: | ---: | ---: |
| A | 12 | 50 | 600 |
| B | 12 | 200 | 2,400 |
| C | 48 | 50 | 2,400 |
| D | 120 | 200 | 24,000 |

Option B has the same number of instances as A, but a 4x larger window. Option C has the same window as A, but 4x as many instances. Both B and C have an equivalent bucket scale under the (N \times W) model, yet the higher instance count in C also increases the number of state machines, configurations, event publishers, and meters.

Option D combines many instances with a large window, resulting in noticeably higher overhead. If the 120 instances are created per customer or resource, the application also has to manage their lifecycle and avoid retaining unused instances.

These numbers are for relative comparison only. To know actual heap usage, measure on the exact JVM version, Resilience4j version, Micrometer setup, and deployment configuration.

## 12. How to Choose Window Size Based on Traffic

Before choosing a window size, determine:

1. Average and peak traffic of the dependency.
2. Target time to detect an incident.
3. Minimum sample size needed to calculate rates reliably.
4. Normal baseline rate of random errors.
5. Tolerance for false positives versus delayed detection.

For example, for a dependency receiving 100 calls per second, a COUNT_BASED window size of 100 covers roughly one second at that load. When traffic drops to 2 calls per second, the same window may span about 50 seconds. A 30-second TIME_BASED window keeps the observation time span more consistent, though it may have fewer samples during low traffic.

Do not pick a window size based solely on a default number. Test small, medium, and large values under representative load, then observe:

- Time from when the dependency starts failing until the circuit becomes OPEN.
- Frequency of circuit openings caused by random errors.
- Recovery time and oscillation frequency between OPEN and HALF_OPEN.
- Heap usage as the instance count increases.
- Number of time series and size of scraped metrics data.

## 13. Common Performance Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Oversized window for every instance | Increases memory without proportional detection gains | Size the window based on traffic and detection goals |
| Undersized window | Volatile rates, prone to tripping from small samples | Pair window size with minimumNumberOfCalls |
| Creating instances per request or customer | State, windows, and metrics grow with input data | Use fixed instance names per dependency/operation |
| Sharing a config and assuming state is shared too | Each instance still has its own window | Distinguish reusable config from runtime instances |
| Enabling too many dynamic tags | Increases time series and storage cost | Use finite tags; move IDs to logs/traces |
| Blocking I/O inside listeners | Increases latency and can stall event-emitting threads | Keep listeners brief or offload to a bounded executor |
| Logging every call at a high level | Increases I/O and log volume | Use aggregated metrics and selective logging |
| Not measuring heap as instance count grows | Memory pressure and GC issues discovered late | Benchmark with an instance count close to production |

## 14. Measurement and Optimization Workflow

When optimizing Circuit Breakers, follow this sequence:

1. List the dependencies and operation groups that truly need separate Circuit Breakers.
2. Count the expected instances and eliminate dynamic IDs tied to requests, customers, or resources.
3. Choose COUNT_BASED or TIME_BASED based on how you want to define the observation span.
4. Choose window size and minimumNumberOfCalls based on traffic and desired detection time.
5. Use shared configs for similar policies, while keeping separate instances when independent state is required.
6. Enable metrics with a finite tag set and register lightweight event listeners.
7. Generate test load at normal and peak levels; measure heap, GC, CPU, response time, time-to-open, and time-series count.
8. Increase or decrease window size and instance count incrementally, comparing results before finalizing the configuration.
9. Monitor after deployment to catch unexpected growth in instance count or cardinality.

The statistics overhead of Resilience4j depends primarily on the number of instances and each instance's window size, along with the associated metrics and event overhead. Larger windows yield smoother statistics at the cost of more memory and potentially slower change detection; more instances add extra state, windows, and metrics. Using stable IDs, sizing windows for your traffic, and measuring under realistic load allow Circuit Breakers to protect services effectively while keeping operational overhead within limits.

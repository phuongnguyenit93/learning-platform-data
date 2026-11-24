# Jitter to Prevent Synchronized Retries

In Spring Kafka, retries help consumers recover from transient errors such as database timeouts, unavailable HTTP services, or network glitches. However, when many consumers encounter the same incident and wait the same fixed duration, they can resend requests almost simultaneously. A surge of requests hitting at the same instant creates a **retry storm** or **thundering herd**: the recovering dependency is immediately overloaded again, causing failures to repeat.

**Jitter** is a random component added to the retry wait time. Instead of all consumers retrying after exactly one second, each consumer gets a different retry time within a controlled window. Jitter spreads load over time, reduces request spikes, and gives the dependency a better chance to recover.

Jitter does not replace exponential backoff, attempt limits, timeouts, rate limits, or idempotency. It adds timing dispersion to the retry policy so multiple processes do not stay synchronized with one another.

## 1. Why do synchronized retries cause overload?

Suppose a payment service stalls for 5 seconds. There are 200 consumers processing different partitions. All call the service and receive timeouts at nearly the same time. If every consumer uses a one-second `FixedBackOff`, they may all retry together in the very next second.

    Time:            0s       1s       2s       3s
    Consumer A:      FAIL     RETRY    RETRY    RETRY
    Consumer B:      FAIL     RETRY    RETRY    RETRY
    Consumer C:      FAIL     RETRY    RETRY    RETRY
    ...
    Consumer 200:    FAIL     RETRY    RETRY    RETRY

    Result: many requests pile up at the exact same moment

If the dependency can only handle 50 concurrent requests, the retry wave can fill queues, exhaust connection pools, or trigger rate limits. Requests fail again, sparking yet another synchronized retry wave.

This phenomenon can occur even when each consumer retries only a finite number of times. Finite attempt counts prevent infinite loops, but do not by themselves spread out retry timestamps.

### 1.1. Exponential backoff can still synchronize

Exponential backoff increases the wait interval after each failure—for example, 1, 2, 4, 8 seconds. This reduces retry frequency over time, but if many consumers start at the same time and use the same parameters, their retry schedules remain identical.

    Consumer A: 1s -> 2s -> 4s -> 8s
    Consumer B: 1s -> 2s -> 4s -> 8s
    Consumer C: 1s -> 2s -> 4s -> 8s

Jitter offsets those marks:

    Consumer A: 0.3s -> 1.4s -> 2.2s -> 6.1s
    Consumer B: 0.8s -> 0.5s -> 3.7s -> 4.9s
    Consumer C: 0.1s -> 1.8s -> 1.1s -> 7.2s

The numbers above are illustrative only. The goal is to distribute requests across a time window, not to create arbitrary or unbounded wait times.

## 2. How does jitter work?

A retry policy typically has two components:

- **Backoff ceiling:** the expected maximum wait interval for the current retry attempt, usually growing via exponential backoff and capped by a max interval.
- **Jitter:** how the actual wait time is chosen within or around that ceiling.

With exponential backoff:

`ceiling_n = min(maxDelay, initialDelay * multiplier^(n-1))`

Jitter selects an actual delay from the ceiling. For example, with full jitter:

`delay_n ~ Uniform(0, ceiling_n)`

Where `Uniform(a, b)` means every value in the range is selected with a uniform probability distribution. If the ceiling is 8 seconds, consumers can wait anywhere from 0 to 8 seconds instead of all waiting exactly 8 seconds.

Jitter must have clear bounds. A retry should not wait indefinitely, exceed SLAs, or generate more requests than the dependency's capacity.

## 3. Common jitter strategies

### 3.1. Full jitter

Full jitter picks a random wait time from 0 to the exponential ceiling:

`delay = random(0, ceiling)`

For example, ceilings of 1, 2, 4, and 8 seconds:

| Retry attempt | Ceiling | Full jitter delay range |
|---:|---:|---:|
| 1 | 1 second | 0–1 second |
| 2 | 2 seconds | 0–2 seconds |
| 3 | 4 seconds | 0–4 seconds |
| 4 | 8 seconds | 0–8 seconds |

Its strength is wide dispersion and reduced request peaks. Its drawback is that it can pick very short delays, even near 0. If a dependency needs a minimum pause to recover, full jitter may need a floor delay or another strategy.

Full jitter is typically suitable when the primary goal is desynchronizing a large number of clients/consumers and the dependency can accept retries spread evenly across the window.

### 3.2. Equal jitter

Equal jitter keeps half of the ceiling as a minimum wait time, then randomizes within the remaining half:

`delay = ceiling/2 + random(0, ceiling/2)`

For example, if the ceiling is 8 seconds, the actual delay falls in the 4–8 second range.

| Retry attempt | Ceiling | Equal jitter delay range |
|---:|---:|---:|
| 1 | 1 second | 0.5–1 second |
| 2 | 2 seconds | 1–2 seconds |
| 3 | 4 seconds | 2–4 seconds |
| 4 | 8 seconds | 4–8 seconds |

Equal jitter avoids overly early retries, though its spread is narrower than full jitter. Choose this when the dependency needs a minimum pause while still needing call timestamps dispersed.

### 3.3. Decorrelated jitter

Decorrelated jitter uses the previous delay to compute the next range:

`delay_n = random(baseDelay, min(maxDelay, previousDelay * 3))`

This creates a less synchronized retry schedule because each consumer has its own delay sequence. It also avoids every consumer increasing delays along the exact same fixed progression.

Decorrelated jitter is useful when correlation between retry rounds needs to be minimized. However, verify lower bounds, upper bounds, and how `previousDelay` is initialized so unreasonable delays are not produced.

### 3.4. Strategy comparison

| Strategy | Selection range | Characteristics | When to consider |
|---|---|---|---|
| Fixed delay | One fixed value | Simple but easily synchronized | Low load, rare and independent errors |
| Exponential, no jitter | Growing ceiling | Reduces frequency but remains synchronized | Few consumers or no simultaneous bursts |
| Full jitter | 0 to ceiling | Wide dispersion, may retry early | Many consumers recovering together |
| Equal jitter | Half ceiling to ceiling | Guarantees a minimum pause | Dependency needs recovery time |
| Decorrelated jitter | Base to min(max, previous × 3) | Less correlated delay sequences | Many retries and many clients |

No single strategy is best for every workload. Choose based on dependency recovery time, SLAs, consumer count, retry budget, and concurrent request limits.

## 4. Jitter does not replace exponential backoff

If you only add jitter to a fixed interval, retries may be dispersed, but frequency stays high when failures persist. Exponential backoff progressively increases wait times to reduce pressure over time. Combining both mechanisms is usually more effective:

1. Compute the ceiling using exponential backoff.
2. Select the actual delay using a jitter strategy.
3. Cap the maximum delay.
4. Bound the total number of attempts.
5. Route the record to recovery/DLT when retries are exhausted.

Example:

    initialDelay = 500 ms
    multiplier = 2
    maxDelay = 8 s

    Ceiling: 0.5s, 1s, 2s, 4s, 8s, 8s, ...
    Full jitter: random(0, ceiling) for each retry

Capping `maxDelay` prevents wait times from growing forever. Capping `maxRetries` prevents records from being retried indefinitely. Jitter spreads out retries within the same ceiling.

## 5. Applying jitter to blocking retry with DefaultErrorHandler

In Spring Kafka, `DefaultErrorHandler` accepts a `BackOff` object. Built-in implementations such as `FixedBackOff` and `ExponentialBackOff` provide deterministic wait schedules. When many consumers use the same schedule, synchronized retry waves can occur.

To add jitter to blocking retry, you can implement the `org.springframework.util.backoff.BackOff` interface. Each call to `start()` creates a dedicated `BackOffExecution` for a record's retry sequence. Retry count and ceiling state must live inside that execution, not be shared across records.

The example below implements full jitter with an exponential ceiling and a finite retry count:

~~~java
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.LongUnaryOperator;

import org.springframework.util.backoff.BackOff;
import org.springframework.util.backoff.BackOffExecution;

public final class FullJitterExponentialBackOff implements BackOff {

    private final long initialInterval;
    private final double multiplier;
    private final long maxInterval;
    private final int maxRetries;
    private final LongUnaryOperator randomBelow;

    public FullJitterExponentialBackOff(
            long initialInterval,
            double multiplier,
            long maxInterval,
            int maxRetries) {

        this(
            initialInterval,
            multiplier,
            maxInterval,
            maxRetries,
            bound -> ThreadLocalRandom.current().nextLong(bound)
        );
    }

    // Constructor usable in tests to control random values.
    FullJitterExponentialBackOff(
            long initialInterval,
            double multiplier,
            long maxInterval,
            int maxRetries,
            LongUnaryOperator randomBelow) {

        if (initialInterval <= 0
                || maxInterval < initialInterval
                || maxInterval == Long.MAX_VALUE
                || multiplier < 1.0
                || !Double.isFinite(multiplier)
                || maxRetries < 0) {
            throw new IllegalArgumentException("Invalid backoff settings");
        }

        this.initialInterval = initialInterval;
        this.multiplier = multiplier;
        this.maxInterval = maxInterval;
        this.maxRetries = maxRetries;
        this.randomBelow = randomBelow;
    }

    @Override
    public BackOffExecution start() {
        return new BackOffExecution() {

            private int retryCount;
            private long ceiling = initialInterval;

            @Override
            public long nextBackOff() {
                if (retryCount >= maxRetries) {
                    return STOP;
                }

                // Full jitter: choose a millisecond value from 0 to ceiling.
                long delay = randomBelow.applyAsLong(ceiling + 1);

                if (delay < 0 || delay > ceiling) {
                    throw new IllegalStateException(
                        "Random source returned an invalid delay"
                    );
                }

                retryCount++;

                if (ceiling < maxInterval) {
                    double next = Math.ceil(ceiling * multiplier);
                    ceiling = next >= maxInterval
                            ? maxInterval
                            : Math.max(ceiling, (long) next);
                }

                return delay;
            }
        };
    }
}
~~~

This implementation has the following characteristics:

- Each record receives its own `BackOffExecution` when Spring Kafka starts a retry sequence.
- The exponential ceiling starts at `initialInterval` and does not exceed `maxInterval`.
- Full jitter selects a delay between 0 and `ceiling`, in milliseconds.
- `maxRetries` is the number of retries after the initial processing attempt; once exhausted, the execution returns `BackOffExecution.STOP`.
- `ThreadLocalRandom` avoids sharing a mutable `Random` instance across threads.
- The constructor accepting a random source allows deterministic testing of delay schedules.

Example using the constructor with six retries, starting at 500 ms, doubling, and capped at 30 seconds:

~~~java
@Bean
CommonErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    BackOff jitterBackOff =
            new FullJitterExponentialBackOff(
                500L,
                2.0,
                30_000L,
                6
            );

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, jitterBackOff);

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class
    );

    return handler;
}
~~~

The factory must attach this handler to the container:

~~~java
factory.setCommonErrorHandler(commonErrorHandler);
~~~

Ensure the imports and generics of `KafkaTemplate`, `ConsumerFactory`, and the recoverer match the serializers/deserializers in your application. The illustrative code uses Spring Framework's `BackOff` API; verify your project's Spring Kafka/Spring Framework dependencies before integrating.

### 5.1. Adjusting full jitter to enforce a minimum pause

Full jitter can return 0 or a very small value. If a dependency needs at least 200 ms to recover, equal jitter or a lower bound can be used.

With equal jitter:

`delay = floor(ceiling/2) + random(0, ceiling - floor(ceiling/2))`

In code, only replace the delay calculation:

~~~java
long lowerBound = ceiling / 2;
long range = ceiling - lowerBound + 1;
long delay = lowerBound + randomBelow.applyAsLong(range);
~~~

This keeps the delay roughly between half the ceiling and the ceiling. If an independent floor is needed, clearly define how to handle cases where `ceiling` is smaller than the floor and ensure the final delay never exceeds `maxDelay`.

## 6. Using jitter with retry topics

Blocking retry holds the record in the current consumer thread while waiting on backoff. This fits when partition order must be preserved and retry intervals are relatively short. For long waits, retry topics can separate the failing record from the main topic so the consumer continues processing other records.

Spring Kafka supports retry topics via `@RetryableTopic`. The backoff annotation may support randomization depending on the library version; check the attributes of `org.springframework.kafka.annotation.BackOff` in your exact version before using it. Do not confuse this annotation with `org.springframework.retry.annotation.Backoff`, as they belong to two different mechanisms.

Example configuring retry topics with exponential backoff:

~~~java
@RetryableTopic(
    attempts = "5",
    backoff = @BackOff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 30_000
    ),
    dltTopicSuffix = ".DLT"
)
@KafkaListener(
    topics = "orders",
    groupId = "order-service"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

If your version supports a random attribute on the backoff annotation, it can be enabled to randomize wait intervals according to the semantics defined by that version. Verify the actual delay calculation and retry count in integration tests. If the version lacks randomization, custom retry-topic routing or a separate delay mechanism can be used; do not assume or invent a non-existent annotation attribute.

Retry topics can alter processing order. Record A fails and is routed to a retry topic, while record B behind it continues processing on the main topic. By the time A returns, B may have already completed before A. If the business requires per-key ordering, evaluate blocking retry, aggregate versioning, or a per-key coordination mechanism.

## 7. Choosing blocking retry vs. retry topics with jitter

| Criterion | Blocking retry with DefaultErrorHandler | Retry topic |
|---|---|---|
| Where waiting happens | Inside the consumer processing thread | Broker holds the record in a retry topic |
| Impact on main partition | May hold subsequent records waiting | Main topic can continue |
| Ordering | Easier to preserve partition ordering | Can alter ordering |
| Jitter | Use custom `BackOff` | Use random backoff if supported by version, or custom delay strategy |
| Best suited for | Short retries where ordering matters | Long retries where isolating failed records is desired |
| Operations | Monitor backoff and consumer polls | Monitor retry topics, lag, and DLT |

Jitter only spreads out retry timing. It does not solve main-partition blocking, nor does it preserve ordering when moving to retry topics.

## 8. Jitter across multiple retry layers

A single request can be retried at multiple layers:

- An HTTP client inside the listener.
- Spring Retry or a resilience library.
- Spring Kafka's `DefaultErrorHandler`.
- Retry topics.
- Another downstream service.

If each layer has three attempts, the actual total number of requests can be far higher than what any single configuration suggests. Jitter at individual layers will not help either if the overall retry budget is unmanaged.

For example, a listener calls an HTTP client configured with three attempts; then the listener still throws an exception and `DefaultErrorHandler` retries four more times. A single record can generate up to twelve HTTP calls if every listener invocation exhausts all three internal attempts.

Define an overall retry budget:

1. Which layer owns primary retries?
2. What is the maximum total number of dependency calls?
3. What is the maximum total processing duration?
4. Which layer decides to move to the DLT?
5. Which layer is responsible for alerting?

If a dependency already has its own retries, reduce retries at the listener or set a smaller attempt count. Avoid letting multiple layers retry unboundedly together.

## 9. Jitter and dependency load limits

Jitter offsets request timing, but does not place a cap on total concurrent requests. When the number of consumers is very large, even requests spread across a window can exceed dependency capacity.

Combine jitter with protective mechanisms:

- **Timeout:** bound the duration of a single dependency call.
- **Concurrency limit:** cap the number of concurrent requests.
- **Rate limit:** cap the number of requests per unit of time.
- **Circuit breaker:** stop calling the dependency when errors exceed a threshold, then probe recovery in a controlled way.
- **Bulkhead:** isolate pools/threads/connections so one dependency cannot consume all resources.
- **Retry budget:** bound total attempts or the ratio of retries to original requests.

For example, if an API only allows 100 requests/second, jitter cannot guarantee all consumers stay under that limit. An appropriate rate limiter or quota is needed. When an API returns 429 or 503, honor `Retry-After` if the application and retry mechanism can utilize that value.

Do not scale consumers out to compensate for an already overloaded dependency. Scaling out can increase concurrency and accelerate the rate of failing requests. Reduce load, apply backpressure, or pause consumers according to operational policy.

## 10. Jitter and idempotency

Retries can happen after the dependency has already executed a side effect, but the response was lost. For instance, a payment API recorded the transaction, yet the client timed out. The consumer retrying the request can create a second payment if the API does not support idempotency.

Jitter only changes retry timing; it does not prevent duplicates. For every business event:

- Keep `eventId` stable across all retry attempts.
- Pass `eventId` as an idempotency key to the API if the API supports it.
- Persist a processing marker in the same database transaction as the business change.
- Use unique constraints or conditional upserts.
- Preserve `eventId` when moving records through retry topics or DLT redrive.

If the listener has committed the database transaction but the Kafka offset has not yet committed, the record can be redelivered. Consumers must be idempotent even when jitter is configured accurately.

## 11. Choosing jitter parameters per SLA

Parameters to determine:

| Parameter | Meaning | How to choose |
|---|---|---|
| `initialDelay` | Ceiling of the first retry | Long enough for brief glitches to self-recover |
| `multiplier` | Ceiling growth factor | Usually greater than or equal to 1 |
| `maxDelay` | Maximum ceiling | Must not exceed SLA-permitted wait time |
| `maxRetries` | Number of retries after the first attempt | Based on the retry budget |
| `jitter strategy` | Full, equal, or decorrelated | Based on dispersion needs and minimum delay |
| `request timeout` | Limit for a single dependency call | Smaller than the overall processing time budget |
| `total deadline` | Total time for all attempts | Must fit the business SLA |

Do not simply sum delays to calculate total time. Each dependency call also involves a request timeout, listener processing time, commit time, and potential rebalances. Expected total time must include all of those components.

Illustrative example:

- initial ceiling: 500 ms.
- multiplier: 2.
- max ceiling: 8 seconds.
- max retries: 5.
- full jitter: each delay randomized from 0 to the current ceiling.

The ceilings are 0.5, 1, 2, 4, and 8 seconds. The maximum total delay is 15.5 seconds, while the theoretical average total delay for full jitter is roughly half the sum of ceilings, or 7.75 seconds. Actual duration also adds the processing time of each request.

If the SLA only allows processing within 10 seconds, this configuration can exceed the deadline once request timeouts are added. Reduce attempt counts, cap `maxDelay`, or choose retry topics if the business permits longer delays.

## 12. Monitoring jitter effectiveness

To tell whether jitter truly reduces retry storms, observe retry timing distributions rather than just total retry counts.

Useful metrics:

**Retry behavior**

- Retry count by topic, partition, and exception class.
- Actual delay chosen for each retry.
- Histogram of intervals between attempts.
- Retry success rate.
- Count of records exhausting retries and moving to the DLT.

**Dependency**

- Request rate and concurrent requests.
- Rate of 429, 5xx, timeout, and connection errors.
- Latency p50, p95, p99.
- Queue depth, connection pool usage, and saturation.

**Kafka consumer**

- Consumer lag and oldest record age.
- Listener record processing duration.
- Rebalance count and duration.
- Number of active consumers.
- Record redelivery rate.

You can compare request-rate histograms before and after enabling jitter. If simultaneous request peaks drop and the dependency recovers faster, jitter is helping spread the load. If total requests still exceed capacity, add rate limiting or reduce concurrency.

Logs should include `eventId`, topic, partition, offset, delivery attempt, chosen delay, and exception class. Do not log full sensitive payloads.

## 13. Testing jitter

Testing must verify both mathematical bounds and system behavior.

### 13.1. Testing BackOffExecution

For a custom `BackOff`, inject a deterministic random source in tests. For example, a random source returning half the bound:

~~~java
FullJitterExponentialBackOff backOff =
        new FullJitterExponentialBackOff(
            500L,
            2.0,
            2_000L,
            4,
            bound -> bound / 2
        );

BackOffExecution execution = backOff.start();

long first = execution.nextBackOff();
long second = execution.nextBackOff();
long third = execution.nextBackOff();
long fourth = execution.nextBackOff();
long finished = execution.nextBackOff();
~~~

With ceilings of 500, 1,000, 2,000, and 2,000 ms, tests can verify that returned delays stay within allowed bounds and the next call returns `STOP`. Because the random source is controlled, test results do not depend on execution timing.

Also verify:

- `initialInterval` must be positive.
- `maxInterval` must not be less than `initialInterval`.
- `multiplier` must be at least 1 and finite.
- `maxRetries` equal to 0 must return `STOP` immediately.
- Delays are non-negative and do not exceed the ceiling.
- Ceiling does not exceed `maxInterval` after many retries.
- Each call to `start()` creates an independent execution.

### 13.2. Distribution testing

With a real random source, do not write tests expecting an exact sequence of random numbers. Instead, run many samples and check that all delays fall within bounds; rough distribution checks can be done with sufficiently large sample sizes, but avoid overly tight statistical thresholds that cause flaky tests.

Integration tests should simulate many consumers failing together and then the dependency recovering. Record timestamps of retry requests to compare clustering before and after jitter. Use sufficient load to observe the difference; a single consumer cannot demonstrate dispersion benefits.

### 13.3. Scenarios to simulate

1. Many consumers receive the same 503 error within the same timeframe.
2. The dependency recovers after a few seconds and enforces a requests/second limit.
3. Retry without jitter to observe synchronized request spikes.
4. Retry with full jitter to measure request distribution.
5. The dependency continues failing past `maxRetries` and records are moved to the DLT.
6. Some calls succeed in side effects yet the response times out; verify idempotency prevents duplicates.
7. Retry topics delay records while other records continue processing; verify impact on ordering.
8. Increase consumer count while the dependency is near saturation; verify rate limits/concurrency limits still protect the dependency.

## 14. Common mistakes when configuring jitter

| Practice | Problem | Remediation |
|---|---|---|
| Using the same fixed delay for all consumers | Consumers can retry in lockstep | Add jitter to backoff |
| Using exponential backoff alone | Retry schedules remain synchronized if started together | Combine with randomization |
| Jitter without max delay | Wait times can exceed SLAs | Set a maximum ceiling |
| Unlimited retries | Failing records hold resources and can prolong lag | Bound attempt counts and add recovery |
| Full jitter producing tiny delays | May retry before the dependency can recover | Use equal jitter or a floor delay |
| Adding jitter without rate limiting | Total requests can still exceed capacity | Cap concurrency and request rate |
| Multi-layer retries without a budget | Dependency call counts multiply | Define an overall retry budget |
| Generating a new `eventId` on each attempt | Duplicates cannot be recognized | Keep `eventId` stable |
| Assuming timeout means no side effect occurred | Can create duplicate transactions or updates | Use an idempotency key |
| Measuring only total retry count | Cannot tell if requests are still synchronized | Monitor delay histograms and request rates |

## 15. Production rollout workflow

When introducing jitter to a running consumer group:

1. Measure baseline: retry rate, dependency latency, request bursts, and consumer lag.
2. Classify exceptions so only recoverable errors are retried.
3. Choose blocking retry or retry topics based on ordering and wait times.
4. Choose full jitter, equal jitter, or decorrelated jitter.
5. Set initial delay, multiplier, max delay, and max retries per SLA.
6. Ensure dependencies have timeouts and consumers have idempotency.
7. Limit concurrency or request rate if the dependency has quotas.
8. Roll out initially to a subset of consumers or an independently observable workload.
9. Compare retry request histograms, dependency saturation, lag, and DLT before/after.
10. Expand configuration after confirming dependency stability and appropriate retry budget.

When rolling back, keep in mind that removing jitter can make retries synchronize again. Do not change backoff while a large volume of records is pending without observing the impact on the consumer group.

## 16. Principles for using jitter

- Use jitter when multiple consumers or clients may hit the same error and retry simultaneously.
- Combine jitter with exponential backoff and max delay.
- Bound attempt counts and total retry duration.
- Choose full jitter when wide dispersion is needed; choose equal jitter when a minimum pause is needed.
- Use a custom `BackOff` for `DefaultErrorHandler` if the API version does not provide a suitable strategy.
- For retry topics, verify the annotation's random backoff capabilities in the exact Spring Kafka version.
- Maintain an overall retry budget when multiple retry layers exist.
- Use timeouts, rate limits, concurrency limits, and circuit breakers to protect dependencies.
- Keep `eventId` stable and make side effects idempotent.
- Monitor delay distributions, request rates, dependency saturation, consumer lag, and DLTs.
- Test multiple consumers failing together and the dependency recovering under load.

Jitter breaks up synchronized retry cadences by spreading out call timestamps. When combined with exponential backoff, retry limits, dependency protections, and idempotency, Spring Kafka consumers can recover from incidents without triggering another overload wave the moment the dependent service begins operating again.

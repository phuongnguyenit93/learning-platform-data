# Tuning Thresholds with Metrics Instead of Copying Sample Configs

Values such as `failureRateThreshold: 50`, `slidingWindowSize: 100`, or `waitDurationInOpenState: 10s` appear frequently in CircuitBreaker examples. They illustrate the API, but they are not optimal settings for every service. A dependency reading cache in 30 ms, a search API taking 800 ms, and a payment gateway taking several seconds have very different traffic profiles, latency distributions, and risk levels.

With Spring Cloud Circuit Breaker backed by Resilience4j, tune `CircuitBreakerConfig` from measurements of the exact dependency and operation type. The goal is to detect degradation early enough to stop cascading failures while avoiding tripping the breaker over a handful of outlier requests or thresholds misaligned with normal latency.

## Start from SLOs and a Baseline

Before changing configuration, establish the dependency's normal behavior under representative load. Collect data separately for each failure domain, including at minimum:

- **Throughput:** requests per second, total calls per interval, and burst patterns.
- **Latency:** p50, p90, p95, p99, and meaningful max latency; never look only at averages.
- **Errors:** timeouts, connection errors, server errors, protocol errors, and business errors categorized separately.
- **Concurrency:** in-flight calls, queues, connection pool limits, and Bulkhead rejections.
- **Recovery time:** how long the dependency takes to return to normal latency and error rates after an incident.
- **Time budget:** end-to-end request deadline, HTTP client timeouts, and how long the caller can afford to wait.

The baseline should cover peak hours, low traffic, bursts, and requests of varying complexity. A single aggregate p95 across an entire API can hide a slow endpoint; when operations have very different characteristics, separate them into distinct breakers or measurement groups.

The caller's SLO turns metrics into concrete decisions. For example, if an end-to-end request must finish within 1 second and other steps already consume 250 ms, the dependency has only about 750 ms left in the budget. The slow-call threshold should reflect that budget and the dependency's normal latency rather than a round number copied from an online example.

## Distinguish the Two Rates Evaluated by the Breaker

Resilience4j evaluates failure rate and slow call rate independently. Once the minimum number of calls is recorded, the breaker transitions to `OPEN` if **either rate meets or exceeds** its threshold.

\[
\text{Failure rate} = \frac{\text{Calls recorded as failures}}{\text{Total recorded calls}} \times 100\%
\]

\[
\text{Slow call rate} = \frac{\text{Calls exceeding slowCallDurationThreshold}}{\text{Total recorded calls}} \times 100\%
\]

A single call can be both failed and slow. In that case, total recorded calls increase by one, while the call contributes to both the failure-rate numerator and the slow-call-rate numerator. Do not add the two rates together to form a combined error rate.

For example, suppose a window has 200 recorded calls, with 34 failed calls and 58 slow calls, of which 20 were both failed and slow:

| Metric | Count | Rate |
|---|---:|---:|
| Total calls | 200 | 100% |
| Failed calls | 34 | 17% |
| Slow calls | 58 | 29% |
| Both failed and slow | 20 | 10% |
| In at least one failed/slow group | 72 | 36% |

If `failureRateThreshold` is 20% and `slowCallRateThreshold` is 30%, the breaker does not open on this window. If the slow-call threshold is 25%, the breaker opens because 29% exceeds the threshold, even though the failure rate is only 17%. That behavior shows a service can still return successful responses while being slow enough to hurt callers.

Only exceptions classified as failures contribute to the failure rate. Exceptions ignored via `ignoreExceptions` or a predicate are not counted as regular failures. Therefore, before tuning `failureRateThreshold`, verify `recordExceptions`, `ignoreExceptions`, `recordExceptionPredicate`, and how the HTTP client translates errors into exceptions. Misclassification causes threshold tuning to mask the real issue.

## Choose slowCallDurationThreshold from the Latency Distribution

`slowCallDurationThreshold` is the duration beyond which a call is recorded as slow. Never set it equal to mean latency: the mean is usually much lower than requests in the distribution tail.

A practical starting approach:

1. Measure the dependency's p50, p95, and p99 under normal load and under high load that still meets SLOs.
2. Identify the latency at which requests begin consuming too much of the caller's time budget.
3. Place `slowCallDurationThreshold` above the acceptable normal latency region, yet below the point where callers routinely breach deadlines.
4. Re-check against operations of different complexity and against client timeouts.

For example, suppose p50 is 90 ms, p95 is 260 ms, and p99 is 430 ms; the caller has a 900 ms deadline and other steps consume around 250 ms. An initial threshold around 500 ms is a reasonable hypothesis to test. Setting 200 ms would mark many normal p95 requests as slow. Setting 850 ms would mean most requests have already blown the caller's budget before being marked slow.

This is only a way to pick a starting point, not a rigid formula. Compare the count of calls marked slow against SLOs and actual timeout rates. If the client times out at 700 ms while `slowCallDurationThreshold` is 1 second, timed-out requests may finish before crossing the slow-call threshold. If timeouts should also reflect latency degradation, align the slow threshold with client timeouts and caller budgets.

`slowCallDurationThreshold` does not replace timeouts. It only classifies outcomes so the breaker can compute the slow call rate. Configure connect/read/response timeouts on the HTTP client or `TimeLimiter` to enforce maximum wait times; the two layers serve different purposes.

## Choose failureRateThreshold from Tolerable Error Levels

`failureRateThreshold` sets the maximum failure percentage allowed in the window before the breaker opens. A low threshold reacts sooner but is sensitive to sporadic errors; a high threshold tolerates more errors but can keep sending traffic to a degrading dependency.

To choose the threshold, consider:

- The dependency's baseline error rate under normal conditions.
- The error level the caller can tolerate before breaching its SLO.
- Error severity and whether fallbacks can supply an acceptable alternative.
- How quickly the dependency degrades and how much extra load retries add.
- Sample count in the window to separate random jitter from systemic failures.

For example, suppose a dependency normally has a failure rate below 0.5%, rising to 20–40% during incidents. A 10% threshold can detect issues early, though you should test against random peak-hour errors to confirm it does not false-trip. If baseline errors are already 3% due to a misclassified business exception, a 10% threshold will trip frequently until classification is fixed.

Never use `failureRateThreshold` as a substitute for business policy. "Product not found" or validation errors should not automatically count as dependency failures if callers treat them as normal outcomes. Fix exception classification first, then calibrate the rate.

## Choose COUNT_BASED or TIME_BASED

The window type determines how the breaker aggregates recent outcomes:

| Type | Meaning | Best Suited When |
|---|---|---|
| `COUNT_BASED` | Retains outcomes for up to the most recent N calls | Traffic is fairly steady or evaluation is desired by sample count |
| `TIME_BASED` | Aggregates outcomes over a time span divided into buckets | Traffic fluctuates and the window should reflect a real wall-clock span |

With `COUNT_BASED`, `slidingWindowSize: 100` evaluates at most the last 100 calls. If the dependency receives 1,000 requests/second, the window turns over very quickly; if it receives only 2 requests/minute, replacing old samples takes much longer.

With `TIME_BASED`, `slidingWindowSize: 60` corresponds to a 60-second window. Time buckets are aggregated and expired buckets drop out as the window slides. This mode is useful when you want to evaluate failure rates over a fixed time interval despite shifting traffic.

`minimumNumberOfCalls` is the minimum number of calls recorded before computing rates. Set too low, the first few errors can open the breaker. Set too high relative to actual traffic, the breaker may never collect enough samples to evaluate. For `COUNT_BASED`, choose a value commensurate with window size; for `TIME_BASED`, choose a value normal traffic reliably reaches within the window duration.

For example, an endpoint receiving 20 requests/second averages only about 5 seconds per 100-call window. For a steadier decision over 30 seconds, test `TIME_BASED` with a 30-second window and set `minimumNumberOfCalls` based on expected requests in that span. Conversely, an endpoint receiving 1 request/second should not set a minimum of 100 in a 30-second window, because the sample requirement will rarely be met.

## Choose waitDurationInOpenState and HALF_OPEN Probes

`waitDurationInOpenState` is how long the breaker stays `OPEN` before allowing recovery checks. Too short a duration can cause rapid open/close flapping while the dependency is still unstable. Too long a duration keeps the application on fallback even after the dependency has recovered.

Base this on:

- How long the dependency typically needs to recover from an outage (restarts, autoscaling, failover, or connection pool recovery).
- How much traffic the dependency can safely accept right as it comes back online.
- The cost of fallbacks and how acceptable continued call rejection is.
- The dependency's operational profile: whether it recovers within seconds or needs longer to warm caches and stabilize.

In `HALF_OPEN`, `permittedNumberOfCallsInHalfOpenState` sets how many probes are allowed. Too many probes can overwhelm a barely recovered dependency; too few probes allow a single outlier request to dominate the decision. Size the probe count based on safe intake capacity and the sample size needed for evaluation.

`maxWaitDurationInHalfOpenState` can bound how long the breaker remains in `HALF_OPEN` if probes hang. Ensure this value aligns with per-call timeouts; if a probe can hang longer than the `HALF_OPEN` limit, tune client or `TimeLimiter` timeouts so outcomes return within the expected timeframe.

## Configuration Example from a Hypothetical Metric Set

Suppose a catalog API has the following measurements under representative load:

| Metric | Hypothetical Measurement |
|---|---|
| Peak throughput | 200 requests/second |
| p50 / p95 / p99 | 90 / 260 / 430 ms |
| Baseline failure rate | 0.5% |
| Normal slow call rate at 500 ms mark | 1.2% |
| Caller deadline | 900 ms |
| Typical recovery time | 10–15 seconds |

An initial experimental configuration could be:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 100
        failureRateThreshold: 15
        slowCallRateThreshold: 25
        slowCallDurationThreshold: 500ms
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 5
        maxWaitDurationInHalfOpenState: 5s
```

This is a starting hypothesis to test against those hypothetical measurements, not a default recommendation for every catalog service. A 30-second window at 200 requests/second usually yields well over 100 samples; `minimumNumberOfCalls: 100` prevents premature evaluation on just a few calls. A 15% failure threshold and 25% slow-call threshold sit comfortably above the assumed baselines yet low enough to catch clear degradation. `waitDurationInOpenState` matches the observed recovery duration. Five probes limit initial recovery traffic.

In real deployments, verify `minimumNumberOfCalls` against the lowest traffic period, not only peak hours. If overnight traffic drops to a few requests per second, 100 samples in 30 seconds may not be reached; in that case, use a longer window, a lower minimum, or a separate policy for low-volume instances.

## Tuning Through Controlled Experiments

Do not change multiple parameters at once and draw conclusions from a single run. Use a comparable iterative workflow:

1. **Record baseline:** capture latency percentiles, throughput, errors, concurrency, timeouts, and fallback rates under the current breaker settings.
2. **Form a hypothesis:** for example, "a 500 ms slow-call threshold will catch most requests exceeding budget without flagging normal p99 as slow."
3. **Make controlled changes:** adjust only one related group of parameters, recording config, version, and test load.
4. **Simulate scenarios:** normal load, bursts, sporadic errors, continuous failures, rising latency, timeouts, and recovery.
5. **Measure outcomes:** detection time, false trips, rejected calls, tail latency, fallback count, remaining dependency load, and recovery time.
6. **Compare against SLOs:** verify whether the caller is better protected and whether the dependency has room to recover.
7. **Canary rollout:** apply to a slice of traffic or one replica first, monitor, then expand.
8. **Document the decision:** record the rationale for chosen thresholds, supporting data, and conditions for revisiting them.

Test at least the following scenarios:

| Scenario | What to Observe |
|---|---|
| Normal latency with occasional outliers | Breaker does not open from a few slow requests |
| Sudden spike in failure rate | Breaker opens within a timeframe aligned with SLOs |
| Latency rises while responses still succeed | Slow call rate triggers when needed |
| Ignored business errors | Do not inflate failure rate unintentionally |
| Burst traffic | Window and minimum calls do not make decisions overly twitchy or sluggish |
| Dependency recovers and fails again | HALF_OPEN neither floods with probes nor flaps continuously |
| Low traffic | Breaker gathers enough samples within an acceptable timeframe |

## Post-Deployment Monitoring

Metrics to observe go beyond current state alone. Monitor these together:

- Each breaker's `state` and state transition count.
- `failureRate` and `slowCallRate` over the window.
- Counts of successful, failed, slow, and rejected (`not permitted`) calls.
- Fallback counts and fallback outcomes.
- Dependency and end-to-end request p95/p99 latency.
- HTTP client/`TimeLimiter` timeout counts and in-flight calls.

Resilience4j can export metrics via Micrometer when the right dependencies and Actuator setup are present. Keep instance names low-cardinality; never build breaker IDs from user IDs, request IDs, or URLs with arbitrary parameters. Watch state-transition events to know when breakers open and close, while metrics explain why the rates moved.

If a breaker keeps opening while the dependency shows no signs of degradation, inspect exception classification, `minimumNumberOfCalls`, baseline latency, and thresholds. If a breaker stays closed while callers experience widespread timeouts, check whether those exceptions are recorded, whether the window has enough samples, and whether thresholds are too high. If a breaker flaps repeatedly between `OPEN` and `HALF_OPEN`, review recovery duration, probe count, timeouts, and initial load as the dependency comes back online.

## Tuning Pitfalls

| Pitfall | Consequence | Remedy |
|---|---|---|
| Copying thresholds from examples | Thresholds fail to reflect dependency latency and baseline errors | Measure baseline and SLOs before choosing |
| Using mean latency as slow threshold | Misses tail latency or flags too many normal requests | Use percentiles and time budgets |
| Setting `minimumNumberOfCalls` too low | A few random errors can open the breaker | Choose a representative sample count |
| Setting minimum higher than window traffic can reach | Breaker rarely evaluates rates | Size against throughput and window type |
| Using one config for every dependency | Fast/slow dependencies and varying risks are misjudged | Configure per failure domain |
| Confusing slow threshold with timeout | Requests wait too long even if breaker marks them slow | Configure separate timeouts on client/`TimeLimiter` |
| Testing only peak hours | Config misbehaves under low traffic or bursts | Test across multiple load profiles |
| Raising thresholds just to stop breaker trips | Masks incidents and prolongs cascading failures | Check classification, samples, and fallbacks first |

## Selection Principles

Let metrics dictate thresholds. `failureRateThreshold` reflects acceptable error levels; `slowCallDurationThreshold` reflects the caller's latency budget; `slowCallRateThreshold` reflects tolerable slow-call ratios; window size and `minimumNumberOfCalls` determine sample stability; `waitDurationInOpenState` and `HALF_OPEN` probes reflect dependency recovery time and capacity. After every change, validate with representative load, controlled fault injection, and canary metrics. A good configuration is backed by evidence for a specific failure domain and revisited whenever traffic or SLOs change.

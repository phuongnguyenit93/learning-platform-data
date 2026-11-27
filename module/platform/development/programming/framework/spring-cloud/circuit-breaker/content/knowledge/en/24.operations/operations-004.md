# Monitoring Recovery Load When Multiple Circuit Breakers Enter HALF_OPEN Together

## Why Can Multiple Circuit Breakers Entering HALF_OPEN Cause Overload?

In Spring Cloud Circuit Breaker using Resilience4j, the `HALF_OPEN` state allows a limited number of trial calls to reach the dependency after the Circuit Breaker has remained `OPEN` for long enough. The outcomes of those calls help the breaker decide whether to close the circuit again or reopen it. This mechanism prevents the application from immediately sending full traffic back to an unrecovered dependency.

An operational issue arises when multiple breakers transition to `HALF_OPEN` within a short window. Those breakers may belong to different dependencies, or to the same dependency across multiple application replicas. If they all permit probes simultaneously, a freshly recovering dependency can get hit by a sudden burst of load while its resources are still fragile. It may time out again, causing the breakers to reopen and creating a failed recovery loop.

This phenomenon is often called a *recovery surge* or *thundering herd*. It can occur even when each breaker has a small `permittedNumberOfCallsInHalfOpenState`, because that limit applies per breaker instance within each process rather than automatically acting as a cluster-wide limit.

## Understanding Probe Counts in HALF_OPEN

Resilience4j does not run a separate background health check by default upon entering `HALF_OPEN`. Calls permitted in this state are typically real application calls passing through the Circuit Breaker. `permittedNumberOfCallsInHalfOpenState` determines how many calls are allowed to evaluate recovery. Once enough outcomes are collected, the breaker uses failure and slow-call thresholds to decide whether to transition back to `CLOSED` or return to `OPEN`.

Suppose a service runs six replicas, and each replica has an independent `catalog` Circuit Breaker. If each breaker allows three calls in `HALF_OPEN`, the total probes that can be sent to catalog from this application is:

\[
6 \text{ replicas} \times 3 \text{ probes/replica} = 18 \text{ probes}
\]

If three other applications also call catalog with the same limit, total trial load can be much higher. In addition, one replica may have multiple breaker IDs pointing to the same backend cluster. When calculating the recovery budget, sum every caller source sharing that dependency's capacity.

| Scope | Limit to Understand |
| --- | --- |
| One Circuit Breaker instance | Number of calls permitted in `HALF_OPEN` per that instance's configuration. |
| One application process | Sum of probes from all breakers transitioning to `HALF_OPEN` in that process. |
| All replicas of an application | Sum of probes across all processes; breaker state is not automatically synchronized across replicas. |
| One shared dependency | Sum of probes from every application, route, and replica calling that dependency. |

Do not treat `permittedNumberOfCallsInHalfOpenState` as a system-wide load limit. Calculate the total across breaker count, replica count, and other callers.

## Why Breakers Can Transition Simultaneously

Several common causes exist:

- Multiple breakers opened together during a dependency outage or 5xx burst.
- Breakers share the same `waitDurationInOpenState`, so their wait durations expire around the same time.
- Replicas started or received traffic nearly simultaneously, producing similar failure patterns and transitioning to `OPEN` together.
- `automaticTransitionFromOpenToHalfOpenEnabled` is enabled, causing breakers to transition automatically after the configured wait duration. If many breakers opened around the same time with the same wait duration, transitions can cluster.
- When automatic transition is disabled, a breaker typically transitions when a call arrives after the `OPEN` duration expires. A new wave of traffic can trigger many breakers almost simultaneously.

`HALF_OPEN` does not mean the dependency is healthy. It is a bounded trial phase. A few successful probes do not prove the backend can sustain normal traffic; monitor dependency latency, queues, and resources before considering recovery stable.

## Establishing a Probe Budget

Start by determining the maximum trial load the dependency can safely handle during recovery. For instance, if the dependency can safely handle only 12 concurrent probe requests across the whole system, total `HALF_OPEN` calls from all callers must stay within that budget.

A rough calculation:

\[
P_{total} = \sum_{i=1}^{n} (R_i \times B_i \times H_i)
\]

Where:

- \(R_i\) is the number of replicas of application \(i\).
- \(B_i\) is the number of breakers per replica targeting the protected dependency.
- \(H_i\) is the number of probes permitted per breaker in `HALF_OPEN`.

This is the theoretical maximum if all breakers transition and receive enough calls simultaneously. Actual load depends on traffic, how the factory creates breakers, and when calls arrive. If multiple routes share a breaker ID, do not count them as separate breakers; if routes have distinct IDs pointing to the same backend, sum them all.

Choose a small `permittedNumberOfCallsInHalfOpenState` when a dependency needs gradual recovery. For dependencies with higher capacity, probe count can be increased after measuring real limits. Do not increase probes just to close the breaker faster; the goal is confirming recovery without causing a new load spike.

## Configuring HALF_OPEN Per Dependency

Example Resilience4j configuration with small probe counts and per-dependency thresholds:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 25s
        permittedNumberOfCallsInHalfOpenState: 2
        maxWaitDurationInHalfOpenState: 10s

      payment:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 40
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 40s
        permittedNumberOfCallsInHalfOpenState: 1
        maxWaitDurationInHalfOpenState: 8s
```

`permittedNumberOfCallsInHalfOpenState` limits how many trial calls are allowed. `maxWaitDurationInHalfOpenState` caps how long the breaker can stay in `HALF_OPEN` waiting for trial calls to finish; if probes do not complete within this window, Resilience4j can transition the breaker back to `OPEN` according to version behavior. A value of `0` has special meaning in some configurations and usually indicates no maximum wait limit; check the documentation for your Resilience4j version before changing it.

`waitDurationInOpenState` determines how long to wait before attempting recovery. This example uses 25 seconds for catalog and 40 seconds for payment to illustrate per-dependency policies. Choose numbers based on real recovery times, dependency criticality, and load capacity. Varying wait durations across dependencies helps avoid concentrating all probes at one moment, though it does not stagger state across replicas sharing the same configuration.

`automaticTransitionFromOpenToHalfOpenEnabled` can be enabled if you want the breaker to transition automatically after the `OPEN` duration even without incoming requests. When enabled, pay special attention when multiple breakers share the same wait duration. When disabled, the next call arriving after the wait duration usually triggers the transition. Which approach fits depends on traffic and operational goals; what matters is measuring actual transition timing.

## Staggering Probe Timing

When multiple breakers are open, the risk of synchronized recovery bursts can be reduced by:

1. **Setting distinct open durations per dependency:** not every dependency needs the same `waitDurationInOpenState`. Base durations on each backend's recovery profile and priority.
2. **Using jitter when supported by the provider:** if your Resilience4j version supports configuring a wait interval function (`waitIntervalFunctionInOpenState`), apply bounded jitter instead of a fixed interval. Check the exact version API and ensure wait intervals stay within operational deadlines.
3. **Limiting probes per dependency:** use a Bulkhead or shared admission control mechanism to bound total concurrency to the backend, even when multiple breakers are `HALF_OPEN` together.
4. **Reducing probes per breaker:** start with one or two probes for load-sensitive dependencies, then increase after observing.
5. **Throttling normal traffic during recovery:** prevent full normal traffic and recovery probes from flooding a backend before it stabilizes.

Process-local jitter only shifts timing within that configuration's bounds. If all replicas share a fixed value and start together, they can still synchronize. When a cluster-wide limit is required, use shared enforcement or load control at the appropriate layer; do not assume in-memory Circuit Breaker state coordinates across pods.

## Using Bulkhead and RateLimiter to Protect the Dependency

A Circuit Breaker decides whether to permit calls based on state and prior outcomes. A Bulkhead limits active concurrent calls, while a RateLimiter limits permission rate. Combining them helps control both probes and normal traffic.

Example Bulkhead for catalog:

```yaml
resilience4j:
  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 8
        maxWaitDuration: 0ms
```

This limit applies to calls passing through the Bulkhead within that registry/process scope. Across six replicas, the theoretical combined limit can still reach 48 calls, excluding other callers. For cluster-wide limits, sum across replicas or enforce admission control at a cluster-scoped layer.

When combining Bulkhead with Circuit Breaker, verify decorator ordering. If `BulkheadFullException` is recorded as a dependency failure, the failure rate can climb even though the backend never received the request. Track Bulkhead rejections separately from Circuit Breaker failures; configure predicates or integration order to reflect true causes.

A RateLimiter can pace probes and recovery requests, but a local RateLimiter's quota also multiplies by replica count. If the dependency has a global quota, enforce rate limiting at the gateway, service mesh, or an appropriate shared quota component.

## Retries Can Multiply Probe Load

A `HALF_OPEN` probe can itself be wrapped by Retry. If each probe is attempted up to three times, two permitted probes can generate up to six supplier executions. Across multiple replicas, requests hitting the dependency multiply further by the number of breakers per replica.

During recovery, consider:

- Reducing or disabling automatic retries for probe calls if retries push load past budget.
- If retries remain enabled, retry only transient errors, cap attempt counts, and use backoff.
- Setting an overall deadline so retries do not hold probes open too long.
- Ensuring write operations carry an idempotency key before retrying.
- Measuring actual executions reaching the dependency, not just invocations entering the Circuit Breaker.

A probe that succeeds only after multiple retries may close the breaker even though the backend had to handle far more requests than the configured probe count. When observing recovery, separate invocation counts, retry counts, and actual backend request counts.

## Timeouts and Hung Probes

If probes fail to complete, the breaker can hold `HALF_OPEN` slots for a long time. When all permitted slots are occupied by slow calls, subsequent calls cannot contribute further recovery evidence. Configure connect timeouts, response/read timeouts, or TimeLimiter appropriately for the dependency.

`maxWaitDurationInHalfOpenState` can bound how long the trial phase waits for results depending on the Resilience4j version. It does not replace HTTP client timeouts and does not guarantee a server-side operation was canceled. If the client times out while the server keeps processing, evaluate idempotency and ongoing backend work.

Slow-call thresholds also matter. A freshly restarted backend may return success responses very slowly due to warm-up, cache loading, or connection pool initialization. Looking only at success/failure can close the breaker too early. `slowCallDurationThreshold` and `slowCallRateThreshold` reflect recovery quality, provided they match realistic latency targets.

## Monitoring State and Recovery Load

Operational dashboards should pair Circuit Breaker state with actual dependency load. At minimum, monitor:

| Group | Metrics | Operational Question |
| --- | --- | --- |
| Breaker state | Count of breakers in `OPEN`, `HALF_OPEN`, `CLOSED`; state transition counts. | How many dependencies or replicas are attempting recovery? |
| Probes | Permitted calls in `HALF_OPEN`, plus successful, failed, and slow counts. | Do probes have enough data to decide closing or reopening? |
| Rejections | Circuit Breaker `not permitted` and `BulkheadFullException`. | Are requests blocked due to an open breaker or exhausted capacity? |
| Dependency load | Request rate, concurrency, queue depth, connection pool, CPU, memory. | Can the backend handle current probes and traffic? |
| Latency | p50, p95, p99 of probes and normal requests. | Has backend speed recovered, or is it merely returning slow successes? |
| Retries | Invocations, retry attempts, and actual backend requests. | How much are retries multiplying recovery load? |
| Fallbacks | Fallback count, latency, and fallback failure rate. | How long are users receiving fallback responses? |

Resilience4j's Micrometer integration typically exposes metrics for state, call counts by outcome, failure rate, slow-call rate, and rejected calls. Exact meter names and tags depend on version and registry. Inspect the actual meter list via Actuator metrics or your observability system before writing dashboard queries.

Resilience4j's event publisher can also emit state transition events such as `OPEN` to `HALF_OPEN`, `HALF_OPEN` to `CLOSED`, or back to `OPEN`. Use events for logging or operational notifications. Include breaker name, before/after state, timestamp, and application instance; do not log sensitive request payloads.

## Alerting on Recovery Surges

Do not alert only when a breaker transitions to `OPEN`. Create alerts for these patterns:

- Sudden spike in breakers transitioning to `HALF_OPEN` within a short window.
- Multiple breakers in `HALF_OPEN` simultaneously while dependency concurrency or queues are near limits.
- Rising rejected or slow probes.
- Breakers oscillating `HALF_OPEN` → `OPEN` → `HALF_OPEN`.
- Dependency returning successes while p95/p99 stays elevated or queues fail to drain.
- High fallback rate persisting after breakers begin probing recovery.

When setting alert thresholds, evaluate both absolute counts and rates. One breaker transitioning repeatedly on tiny traffic differs from many breakers transitioning within a few seconds. Tag by dependency, breaker ID, and instance/pod with bounded cardinality. Never use user ID or request ID as a metric tag.

## Runbook When Multiple Breakers Enter HALF_OPEN Together

When dashboards show multiple breakers attempting recovery and dependency load climbing, follow this sequence:

1. **Scope the impact:** list breaker IDs, target dependency, applications, and replicas currently in `HALF_OPEN`.
2. **Calculate total probes:** sum permitted probes across all breakers and replicas; include retries and other callers.
3. **Check backend capacity:** inspect request rate, active connections, queues, CPU, memory, thread pools, and latency.
4. **Slow recovery if needed:** lower probe counts on affected breakers, increase wait durations, or throttle traffic via Bulkhead/RateLimiter at the appropriate scope.
5. **Inspect timeouts and retries:** ensure probes do not hold slots too long and retries do not multiply requests beyond budget.
6. **Observe outcomes:** verify probes finish and breakers either settle in `CLOSED` or return to `OPEN` without prolonged backend overload.
7. **Ramp load gradually:** once latency and queues stabilize, raise concurrency limits or restore traffic step by step.

Do not force breakers to `CLOSED` just to clear alerts. If the backend cannot handle the load yet, closing circuits en masse can send full traffic back and re-trigger the outage. If configuration must change during an incident, log the breaker ID, old/new values, timestamp, and operator so changes can be reverted.

## Testing Concurrent Multi-Breaker Recovery

In a test environment, create multiple independent breakers targeting a simulated dependency. Force the dependency to fail so all breakers enter `OPEN`, then restore the dependency with a low concurrency limit. Observe whether the breakers enter `HALF_OPEN` simultaneously and whether total probes exceed processing capacity.

Scenarios to test:

| Scenario | What to Verify |
| --- | --- |
| Multiple breakers share `waitDurationInOpenState` | Do probes cluster within a short window? |
| Open durations are staggered | Does the recovery request peak drop? |
| Each breaker allows only one probe | Do total probes across many replicas still exceed budget? |
| Retries enabled on probes | Are actual backend requests multiplied? |
| Hung probes | Do timeouts and `HALF_OPEN` wait limits release the trial phase? |
| Dependency succeeds slowly | Do slow-call thresholds prevent closing the circuit too early? |
| Bulkhead full during `HALF_OPEN` | Are rejection errors miscounted as dependency failures? |

Tests must observe both actual calls hitting the dependency and state transitions of each breaker. Testing a single breaker in isolation is insufficient to catch multi-replica recovery surges.

## Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `permittedNumberOfCallsInHalfOpenState` as a cluster limit | Total probes multiply by replica and breaker count. | Budget probes across the full dependency and caller scope. |
| Using the same open duration for every dependency | Many breakers attempt recovery at the exact same moment. | Choose wait durations per failure domain and consider bounded jitter. |
| Raising probe counts so breakers close faster | A freshly recovering dependency gets overloaded again. | Start with small probe counts and increase after measuring. |
| Ignoring retries when sizing load | Actual requests exceed permitted probe counts. | Count retry attempts and real backend requests. |
| Omitting timeouts | Slow probes hold `HALF_OPEN` slots too long. | Set client timeouts and appropriate wait bounds. |
| Counting Bulkhead rejections as dependency errors | Breakers open because the application exhausted local capacity. | Track and classify rejection errors separately. |
| Watching only breaker state | Misses that the backend is still slow or queues remain full. | Correlate state with dependency latency, concurrency, and resources. |

Monitoring multiple Circuit Breakers entering `HALF_OPEN` together is a system-wide recovery load orchestration problem. Sum probes across all replicas and callers, stagger trial timing, bound concurrency, control retries and timeouts, and track dependency latency and queues. When probes stay within budget and load ramps gradually, Circuit Breakers can confirm recovery without triggering another overload wave.

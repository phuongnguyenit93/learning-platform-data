# Capacity, Latency, and Concurrent Call Estimation

When deploying a Circuit Breaker in Spring Cloud, you need to know how many calls a dependency can handle, how latency changes as load rises, and how many requests are waiting at the same time. These three metrics are directly tied to service protection: throughput measures processing speed, latency measures completion time, and concurrent calls measure how much work is occupying resources at a given moment.

A Circuit Breaker stops sending new calls when a dependency shows signs of errors or slowness. However, it does not automatically limit concurrent calls while CLOSED. To estimate and control load, you must combine empirical measurements, Little's Law, timeouts, Bulkheads, connection pool limits, and load testing. Accurate estimation helps you choose grounded concurrency limits, lowers the risk of thread or connection exhaustion, and avoids building queues when a dependency is already saturated.

## 1. Three Core Metrics to Measure

**Throughput** is the number of calls completed per unit of time, usually measured in requests per second (RPS) or calls per second. Distinguish between incoming API request throughput and call throughput to a specific dependency. A single request might call Catalog twice, Inventory once, and Payment once; therefore, dependency call rate can exceed incoming request rate.

**Latency** is the time from when an operation starts until a response is received. Track multiple percentiles instead of relying only on the mean:

- **p50:** half of all calls complete in this time or less.
- **p95:** 95% of calls complete in this time or less.
- **p99:** 99% of calls complete in this time or less.

p95 and p99 uncover tail latency—the slow outliers even when most requests are fast. Mean latency is useful for estimating in-flight concurrency, whereas high percentiles must be tracked to set timeouts and uphold SLOs.

**In-flight concurrency** is the number of calls that have started but not yet finished at the same instant. A dependency might handle 500 calls/second with a 100 ms latency and average only about 50 in-flight calls. If latency climbs to one second while throughput stays at 500 calls/second, average in-flight calls climb to around 500.

| Metric | Common Unit | Question Answered |
|---|---|---|
| Throughput | requests/s or calls/s | How many calls does the system complete per second? |
| Latency | ms or s | How long does a single call take to finish? |
| In-flight concurrency | number of calls | How many calls are holding resources at the same time? |
| Error rate | % | What share of calls end in error? |
| Saturation | %, queue depth, pool usage | How close are resources to their limits? |

Measuring the right scope is critical. When calculating load for Catalog, use the call count sent to Catalog—not total API RPS if each request only calls Catalog a fraction of the time.

## 2. Using Little's Law to Estimate Concurrency

Little's Law describes the relationship between the average number of items in a stable system, the rate at which items move through the system, and the average time an item spends in the system:

\[
L = \lambda \times W
\]

Where:

- \(L\): average number of work items in the system.
- \(\lambda\): average throughput, in items per second.
- \(W\): average time a work item spends in the system, in seconds.

For calls to a dependency, you can use:

\[
N_{\text{in-flight}} \approx \lambda_{\text{calls}} \times W_{\text{mean}}
\]

For example, if Catalog receives an average of 400 calls per second and each call takes an average of 250 ms, or 0.25 seconds:

\[
N = 400 \times 0.25 = 100
\]

Thus, Catalog has roughly 100 in-flight calls on average under steady load. This figure is not a maximum bound. When traffic spikes or latency rises, actual concurrency can be considerably higher.

Little's Law applies to a system with steady flow over the measurement interval. Use throughput and average time measured across the same boundary. If the measured duration includes queueing time, \(L\) includes queued work as well; if you only want calls executing at the dependency, measure from dispatch to completion at that exact boundary.

## 3. Calculating Dependency Call Rate from Incoming Requests

A single business request may trigger multiple calls to the same dependency. To estimate accurately, compute the average number of calls per request and the amplification from Retry.

You can use the formula:

\[
\lambda_{\text{dependency}} =
\lambda_{\text{requests}}
\times C_{\text{calls/request}}
\times A_{\text{attempts}}
\]

Where:

- \(\lambda_{\text{requests}}\): incoming request rate.
- \(C_{\text{calls/request}}\): average number of dependency calls per request.
- \(A_{\text{attempts}}\): average number of attempts per logical call, including Retry if enabled.

For example, an API receives 600 requests/second. Each request calls Catalog 0.8 times on average because some flows do not look up products. Retry increases average attempts by 10%, so \(A_{\text{attempts}} = 1.1\):

\[
\lambda_{\text{catalog}} = 600 \times 0.8 \times 1.1 = 528
\]

Catalog actually receives around 528 attempts/second. Using only the API's 600 RPS or ignoring Retry would produce the wrong estimate.

When a request calls multiple dependencies, calculate each dependency separately:

| Dependency | Calls/request | Average Attempts | Incoming Requests 600/s | Estimated Calls/s |
|---|---:|---:|---:|---:|
| Catalog | 0.8 | 1.1 | 600 | 528 |
| Inventory | 0.6 | 1.0 | 600 | 360 |
| Pricing | 1.0 | 1.05 | 600 | 630 |

If calls execute in parallel, total in-flight calls inside the application equal the sum of each dependency's concurrency. Overall request completion time may be close to the slowest call plus remaining processing steps, rather than the sum of all dependency latencies.

Measure the actual attempt rate from client metrics whenever possible. The formula above is useful for planning before metrics exist; Retry with backoff, conditional retries, or cancelled requests can shift the attempt factor depending on load and error type.

## 4. Calculating Average Concurrency and Burst Headroom

Once you have the call rate, multiply it by mean latency to estimate average concurrency. Then apply burst data or a headroom factor to estimate peak load.

For example, Catalog receives 528 calls/second with a mean latency of 180 ms:

\[
N_{\text{mean}} = 528 \times 0.18 = 95.04
\]

This indicates about 95 in-flight calls on average. If peak load is 1.4 times the average, a rough burst estimate is:

\[
N_{\text{burst}} \approx 95.04 \times 1.4 \approx 133
\]

The 1.4 burst factor in the example is only an assumption. Replace it with time-series data such as p95/p99 concurrency, per-minute peaks, or flash-traffic scenarios. Do not treat multiplying by a burst factor as an exact law; it is an initial budgeting technique that must be validated by load testing.

Also consider latency rising alongside load. If the dependency slows from 180 ms to 500 ms while the call rate remains 528/s, average concurrency under Little's Law rises to:

\[
N = 528 \times 0.5 = 264
\]

This is the mechanism by which a slow dependency self-amplifies the number of waiting requests. Once threads, connections, or queues fill up, latency can climb even further, creating an overload spiral.

## 5. Dividing the Concurrency Budget Across Instances

Applications typically run multiple replicas or pods. If traffic is distributed evenly, average per-instance concurrency can be estimated by dividing total concurrency by the number of healthy instances:

\[
N_{\text{per-instance}} \approx
\frac{N_{\text{total}}}{R}
\]

Where \(R\) is the number of instances actively receiving traffic. With roughly 133 calls at burst and six instances:

\[
N_{\text{per-instance}} \approx \frac{133}{6} \approx 22.2
\]

This estimate holds only when traffic is fairly evenly balanced. Load balancers can distribute unevenly, and one instance may receive more requests due to long-lived connections, sticky routing, cache locality, or hot shards. Measure concurrency per instance and also account for an unhealthy replica.

With autoscaling, the aggregate concurrency limit scales with replica count if Bulkheads are configured locally per instance. For example, a Bulkhead of 24 calls per pod means:

- 4 pods: theoretical total limit of 96.
- 6 pods: theoretical total limit of 144.
- 8 pods: theoretical total limit of 192.

If the backend can only safely sustain 150 concurrent calls, scaling from 6 to 8 pods can push the application's aggregate limit past backend capacity. Size limits against the maximum pod count, not just the current pod count. If a cluster-wide limit is needed, use distributed quota/concurrency control or enforce limits at an appropriate gateway/backend layer; an in-JVM Bulkhead normally applies locally only.

## 6. Estimating Safe Dependency Capacity

Safe concurrency cannot be inferred from latency alone. You need to identify where the dependency begins to saturate using load tests and operational metrics.

Limits to examine include:

- CPU and memory of the dependency.
- Number of worker threads or event loops available to process work.
- Database and HTTP client connection pools.
- Server-side concurrent connection or request limits.
- Queue depth and queue wait times.
- Limits of shared downstream services such as databases, caches, or message brokers.
- p95/p99 latency and error rate as load increases.

Suppose load testing shows that Catalog's p99 and errors spike around 180 concurrent calls. The team may choose a lower protective budget, such as 80%:

\[
C_{\text{budget}} = 180 \times 0.8 = 144
\]

Here, 144 is the target concurrency budget across all callers accounted for in the example, not a Resilience4j default. The remaining margin provides headroom for traffic variance, other clients, and operational overhead. If Catalog also serves traffic from other systems, subtract their load before allocating a budget to this application.

A safe limit must be verified against realistic traffic. Whenever backend configuration, replica count, connection pools, or query profiles change, the saturation point can shift as well.

## 7. Using Bulkhead to Limit Concurrent Calls

Circuit Breaker and Bulkhead serve different roles:

- Circuit Breaker tracks outcomes, failure rates, and slow calls to decide between CLOSED, OPEN, or HALF_OPEN.
- Bulkhead limits how many tasks or calls may execute concurrently.
- TimeLimiter bounds how long an operation is allowed to wait.
- Connection pools limit how many connections can be used at the client layer.

When a Circuit Breaker is CLOSED, it can allow many concurrent calls. If the dependency slows down, calls keep holding connections and resources until they complete or time out. A Bulkhead enforces a concurrency cap so one dependency cannot consume all resources meant for other operations.

Example Semaphore Bulkhead configuration for Catalog:

~~~yaml
resilience4j:
  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 24
        maxWaitDuration: 0
~~~

With this illustrative configuration, each application instance permits at most 24 concurrent Catalog calls through that Bulkhead. Once slots are exhausted, new calls are rejected rather than queueing indefinitely. The application can then fall back or return an overload error according to policy.

If six pods each have a Bulkhead limit of 24, the theoretical aggregate limit is 144. Account for the maximum number of active pods so you do not exceed the backend budget. If traffic is skewed across pods, one pod's Bulkhead may fill up while another still has slots; monitor load distribution and consider shared-tier limits where appropriate.

A thread-pool Bulkhead adds a dedicated thread pool and queue. A queue can absorb short bursts, but a large queue increases wait times and holds requests longer. Do not use an unbounded queue to mask an under-provisioned dependency.

## 8. Combining Bulkhead with Timeouts and Circuit Breaker

A complete protection policy typically combines all three mechanisms:

1. **Bulkhead** caps how many calls execute at the same time.
2. **TimeLimiter or client timeout** bounds how long a call waits.
3. **Circuit Breaker** blocks new calls when statistics show the dependency is degraded.

Example limit configuration for Catalog:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 30
        failureRateThreshold: 50
        slowCallDurationThreshold: 500ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 5

  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 24
        maxWaitDuration: 0

  timelimiter:
    instances:
      catalog:
        timeoutDuration: 700ms
        cancelRunningFuture: true
~~~

These values are examples that must be tuned to your SLOs and load test measurements. **slowCallDurationThreshold** lets the Circuit Breaker identify slow calls; **timeoutDuration** sets the wait deadline; **maxConcurrentCalls** bounds concurrent work. In this example, the 700 ms timeout is larger than the 500 ms slow-call threshold so that calls can be classified as slow before timing out, depending on the integration style and when outcomes are recorded.

When a Bulkhead runs out of slots, a rejection exception can occur before any call reaches the dependency. Classify this error separately from backend failures. If the Circuit Breaker records Bulkhead rejections as dependency failures, it may trip because of a local caller limit. Exception policies and decorator ordering must reflect the intended operational semantics.

When the Circuit Breaker is OPEN, new calls are rejected before consuming dependency slots. In HALF_OPEN, only the configured number of probes are permitted to test recovery. The Bulkhead still bounds resources while probes and other operations run.

## 9. Retry Increases Concurrency and Dependency Load

Retry can increase the number of attempts per logical request. If a dependency suffers transient failures, many concurrent requests may retry together, amplifying load right when the backend is already degraded. This phenomenon can trigger a retry storm.

When estimating concurrency, use the attempt rate rather than only the logical request rate. For example, 400 logical calls per second with an average of 1.5 attempts per call produces 600 attempts/second. At 300 ms mean latency:

\[
N = 400 \times 1.5 \times 0.3 = 180
\]

Ignoring Retry would yield an estimate of 120 calls—underestimating load by 50%.

Control principles:

- Cap **maxAttempts**.
- Retry only recoverable errors and operations safe to repeat.
- Use backoff and jitter to spread out retry timing.
- Set per-attempt timeouts and an overall time budget.
- Do not keep retrying when the Circuit Breaker is OPEN.
- Track retry rates and actual attempt counts per dependency.

For write operations, use idempotency keys or status-lookup mechanisms to avoid duplicate execution if the caller times out after the server already completed the work. When capacity planning, update the attempt factor using production telemetry instead of keeping a static assumed multiplier.

## 10. Special Considerations for Reactive Applications

Reactive execution does not allocate a dedicated thread per request, yet that does not make concurrent calls free or unlimited. Every pending request can still hold connections, sockets, buffers, memory, subscriptions, and processing slots at the dependency. When in-flight Publishers pile up, the application can still exhaust connection pools or overload the backend.

In a batch processing pipeline, Reactor lets you bound concurrent element processing using the concurrency parameter on **flatMap**:

~~~java
Flux<Product> products =
    Flux.fromIterable(productIds)
        .flatMap(catalogClient::getProduct, 24);
~~~

The parameter `24` limits the number of concurrent inner Publishers within that `Flux` execution. It is not a global limit across all HTTP requests in the application. If 100 independent requests each create a `Flux` with concurrency 24, total calls can be far higher. To enforce a limit shared across requests, use a Bulkhead or a shared semaphore/connection pool at the appropriate scope.

In WebFlux:

- Use the reactive Circuit Breaker factory and keep `Mono`/`Flux` throughout the pipeline.
- Apply Reactor or client timeouts matching the operation's budget.
- Avoid calling **block()** on the event loop.
- Limit concurrency at the scope that genuinely needs protection, not only within a single batch.
- Monitor in-flight requests, connection pools, pending acquires, and cancellations.
- Verify that the HTTP connector propagates cancellation down to the underlying network request.

Backpressure regulates item emission and consumption within a single pipeline, but it does not automatically impose a global cap across all calls to a dependency. Combine the right mechanisms for the target load scope.

## 11. Reading Metrics to Identify Saturation Points

Do not monitor CPU alone. A dependency can be bottlenecked by connection pools, databases, or queues while CPU still looks low. Combine multiple signals:

| Signal | Warning Sign | Investigation Action |
|---|---|---|
| Calls/s | Rapid increase or exceeding baseline | Check traffic, fan-out, and Retry |
| In-flight calls | Rising steadily while throughput stays flat | Check latency, queues, and hung requests |
| p95/p99 latency | Steep climb as load rises | Locate saturation point and bottleneck |
| Error/timeout rate | Rising alongside latency | Inspect dependency, network, and timeouts |
| Connection pool usage | Hitting max or rising pending acquires | Review pool size, connection hold time, and client timeouts |
| Bulkhead rejection | Spiking during bursts or latency increases | Review concurrency limits and backend capacity |
| Circuit Breaker state | Frequent transitions to OPEN | Inspect failure/slow-call rates and window config |
| Queue depth | Growing without draining | Reduce admission, cap queues, or scale capacity with verification |

A dangerous pattern is flat completed throughput paired with rising in-flight calls and latency. That indicates work is accumulating faster than it can finish. Admitting more requests only lengthens queues without improving throughput.

Inspect both per-pod and cluster-wide metrics. Aggregate metrics can mask a hot pod, a slow shard, or a locally exhausted connection pool.

## 12. End-to-End Estimation Example

An ordering API runs six Gateway pods and calls Catalog. Peak-hour measurements show:

- Incoming requests: 600 requests/second.
- Catalog call rate per request: 0.8 calls/request on average.
- Average Retry attempts: 1.1 per logical call.
- Catalog mean latency: 180 ms.
- Load testing shows Catalog begins saturating around 180 concurrent calls.
- The team reserves 20% capacity as headroom for variance and other traffic.

**Step 1: Compute attempt rate to Catalog**

\[
\lambda = 600 \times 0.8 \times 1.1 = 528 \text{ calls/s}
\]

**Step 2: Compute average concurrency**

\[
N_{\text{mean}} = 528 \times 0.18 \approx 95
\]

**Step 3: Estimate burst concurrency**

If the observed burst factor is 1.4:

\[
N_{\text{burst}} \approx 95 \times 1.4 \approx 133
\]

**Step 4: Compute safe concurrency budget**

\[
C_{\text{budget}} = 180 \times (1 - 0.20) = 144
\]

**Step 5: Divide the limit across six pods**

\[
C_{\text{pod}} = \frac{144}{6} = 24
\]

The team can start testing with a Semaphore Bulkhead capped at 24 Catalog calls per pod. The theoretical aggregate limit is 144 across all six pods. The burst estimate of 133 sits below the 144 budget, though the margin is tight; watch for traffic skew and single-replica failures.

If the system autoscales to eight pods while keeping 24 slots per pod, the total limit becomes 192, exceeding the 144 budget. Whenever maximum replica count changes, recalculate the per-pod limit or use a global limit. If one pod goes down, total admission capacity also drops; the system must tolerate controlled rejections or maintain reserve capacity rather than pushing overload onto the remaining five pods.

These calculations are a starting point. Only load testing with realistic traffic mix, latencies, and Retry rates confirms whether the Bulkhead sizing is appropriate.

## 13. Practical Measurement and Calibration Workflow

Follow this sequence:

1. **Define measurement boundaries:** select the API, dependency, and operation to protect.
2. **Collect a baseline:** measure RPS, calls/s, mean latency, p95/p99, error rate, and in-flight concurrency.
3. **Calculate call amplification:** determine calls per request and the Retry attempt factor.
4. **Estimate concurrency:** multiply attempt rate by mean latency using Little's Law.
5. **Measure the saturation point:** ramp load systematically in load tests while watching throughput, latency, queues, connection pools, and system resources.
6. **Set a budget:** reserve headroom for bursts, external traffic, and distribution skew.
7. **Size the Bulkhead:** compute limits from total capacity and maximum replica count; define behavior when slots run out.
8. **Choose timeouts and Circuit Breaker thresholds:** base them on SLOs, latency distributions, and observed failure patterns.
9. **Test failure modes:** inject dependency slowness, errors, connection exhaustion, or an open Circuit Breaker; verify fallbacks and admission control.
10. **Calibrate after deployment:** compare production metrics against estimates and update whenever traffic mix or architecture changes.

Do not raise a Bulkhead limit simply because rejections appear. First verify whether the backend has spare capacity. If the dependency is already saturated, raising the limit merely pushes more work into an already backed-up queue. Conversely, if the backend has ample headroom and the Bulkhead is overly restrictive, raise it gradually and re-measure.

## 14. Common Estimation Mistakes

1. **Using API RPS instead of dependency call rate.** Ignoring fan-out undercounts actual calls.
2. **Ignoring Retry.** Attempt rate can be substantially higher than logical call rate.
3. **Plugging p99 into Little's Law instead of mean latency without understanding why.** Little's Law uses mean time; high percentiles are for setting timeouts and inspecting tail latency.
4. **Dividing concurrency by current replica count and forgetting autoscaling.** Local per-pod limits can overshoot backend capacity when pods scale out.
5. **Treating Circuit Breaker as a concurrency limit.** When CLOSED, many calls can still run concurrently; a Bulkhead or client limit is required.
6. **Setting queues too large.** Queues mask overload while inflating latency and request hold times.
7. **Looking only at CPU.** Connection pools, databases, threads, event loops, or networks often bottleneck before CPU.
8. **Using `flatMap` concurrency as a global cap.** That limit typically scopes only to a single subscription, not across all requests.
9. **Omitting traffic from other clients.** One application's budget must fit inside the dependency's remaining capacity.
10. **Failing to re-measure after changes.** Adding replicas or changing timeouts, Retry, or payloads alters latency and concurrency.

## Conclusion

Estimate concurrent calls by measuring the dependency attempt rate and mean latency, then applying Little's Law: \(N \approx \lambda \times W\). Use load testing to locate the saturation point, reserve headroom, and calculate limits against maximum replica count. A Circuit Breaker detects dependency degradation and stops new calls when OPEN; a Bulkhead caps concurrency, timeouts cap wait duration, and Retry can amplify load. Combining these controls with per-dependency and per-instance metrics keeps services resilient when traffic spikes or dependencies slow down.

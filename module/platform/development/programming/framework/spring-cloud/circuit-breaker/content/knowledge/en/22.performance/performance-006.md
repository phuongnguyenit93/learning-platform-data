# Measuring Overhead Under Normal Load, Continuous Failures, and Open Circuit

Evaluating Circuit Breaker performance requires separating the cost it adds to a normal call from the protection it delivers when a dependency fails. In the `CLOSED` state, every request is checked for permission and its outcome is recorded in the sliding window; this is the overhead to measure when the system is healthy. Under continuous failures, the Circuit Breaker must gather enough samples to decide to open. Once `OPEN`, requests are rejected quickly and should stop adding load to the dependency.

There is no single fixed overhead figure that applies to every application. Results depend on the Resilience4j/Spring Cloud versions, synchronous versus reactive execution, window size, thread count, logging, metrics, fallbacks, HTTP client, and background load. Measurements must be taken in a repeatable environment with identical offered load and resource configuration.

## 1. Define the Questions and Measurement Scope

Before running benchmarks, clarify which layer you are measuring:

- **Library micro-overhead:** the cost of calling directly versus calling through a Circuit Breaker inside the same JVM, with no network or external server. Use JMH to isolate the cost of state checks, outcome recording, and call rejection.
- **Application overhead:** the cost of factories/proxies, fallbacks, metrics, logging, executors, serialization, and HTTP clients in a realistic Spring service.
- **End-to-end behavior under load:** throughput, latency, and resource usage as requests flow through the API, Circuit Breaker, and dependency. Use load tests against a simulated dependency with controllable latency and failures.

JMH does not replace load testing. Microbenchmarks measure the cost of an operation inside the JVM; load tests reveal how many requests the system can serve, how latency behaves, and whether threads or connections saturate.

## 2. Metrics to Collect

| Category | Metrics | Purpose |
| --- | --- | --- |
| Traffic | Request rate, throughput, completed requests, dropped iterations | Is the system keeping up with the offered load? |
| Latency | p50, p95, p99, and max latency | Does overhead affect most requests or tail latency? |
| Errors | HTTP 5xx, timeouts, exceptions, fallbacks, `CallNotPermittedException` | Did requests fail due to the dependency, timeouts, or breaker rejections? |
| Circuit Breaker | State, failure rate, slow-call rate, not-permitted calls, state transitions | When did the circuit open, and did it stay in the expected state? |
| Dependency | Requests reaching the stub, latency, connection count, and errors | When `OPEN`, does traffic to the dependency actually drop? |
| Resources | CPU, heap/RSS, allocation rate, GC pauses, thread count | Does overhead raise CPU or memory cost? |
| Queues | Executor queue, Bulkhead queue, active threads, rejected tasks, connection pool wait | Did the bottleneck shift to another pool or queue? |

Measure API latency separately from dependency call latency. When a dependency takes 500 ms, a few microseconds of Circuit Breaker overhead can be masked inside total request duration. Conversely, when the circuit is `OPEN`, API latency primarily reflects rejection, fallback, and serialization time.

## 3. Design the Test Matrix

Keep the same build artifact, payload, instance count, CPU/memory limits, JVM flags, HTTP client, connection pool, and logging configuration across runs. Change only one variable at a time. A minimal test matrix should include:

| Scenario | State / Condition | Measurement Goal |
| --- | --- | --- |
| A. Direct baseline | Call dependency without a Circuit Breaker; dependency succeeds | Baseline latency, throughput, and CPU/request |
| B. CLOSED, no errors | Circuit Breaker enabled; dependency succeeds steadily | Overhead on the normal call path |
| C. CLOSED, realistic latency | Dependency succeeds with fixed latency or a production-like latency distribution | Impact when network/client dominates total time |
| D. Continuous failures and transition | Dependency returns errors or timeouts continuously until the breaker hits its trip threshold | Requests needed to open, detection time, and pre-open load |
| E. Steady OPEN | Breaker is already open; continue sending the same offered load | Rejection latency, fallback cost, and remaining dependency requests |
| F. HALF_OPEN and recovery | Open duration expires; dependency recovers or keeps failing | Probe count, concurrency, and stabilization time |

Run the baseline and Scenario B through the same processing path as closely as possible. If the baseline skips serialization, the client, or the service layer, the difference no longer represents Circuit Breaker overhead alone.

## 4. Prepare a Simulated Dependency

Use a dedicated mock server or service stub to control responses. Provide configurable modes before each run:

- `success`: returns a successful response with a fixed payload.
- `slow`: returns a response after a fixed delay or controlled latency distribution.
- `error`: returns 5xx errors continuously.
- `timeout`: holds requests longer than the client/`TimeLimiter` timeout.
- `recover`: switches back to returning success after a failure period to measure `HALF_OPEN`.

The stub should count incoming requests, latencies, and response codes. That counter is crucial evidence confirming that an open Circuit Breaker actually stops sending new requests. Run the stub and load generator on separate machines—or at least monitor their CPU—because if the generator saturates, application throughput no longer reflects offered load.

Set an explicit Circuit Breaker configuration in the benchmark profile. For example:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: false
```

With this configuration, the breaker needs at least 10 samples before evaluating failure rate. Once enough samples exist and the failure rate reaches the threshold, the circuit opens. How many requests fail before opening depends on `minimumNumberOfCalls`, window size, failure rate, concurrency, and when calls finish. Do not assume the breaker opens on the very first error.

In the continuous-failure scenario, record when the first request fails, when enough samples arrive, and when the state transitions to `OPEN`. In the `OPEN` scenario, wait for confirmation that the state has opened before starting the steady-state measurement window; otherwise, measurements mix the failure-detection phase with the fast-rejection phase.

## 5. Microbenchmarking with JMH

JMH is well suited for measuring the cost of calling a supplier directly, calling a supplier through a `CLOSED` Circuit Breaker, and the rejection path when the breaker is `OPEN`. Place benchmarks in a separate benchmark module; never run JMH inside a request handler.

Minimal benchmark example:

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.openjdk.jmh.annotations.*;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Fork(3)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
public class CircuitBreakerOverheadBenchmark {
    private Supplier<Integer> direct;
    private Supplier<Integer> closed;
    private Supplier<Integer> openWithFallback;

    @Setup(Level.Trial)
    public void setup() {
        direct = () -> 42;

        CircuitBreaker closedBreaker = CircuitBreaker.of(
                "closed", CircuitBreakerConfig.ofDefaults());
        closed = CircuitBreaker.decorateSupplier(closedBreaker, direct);

        CircuitBreakerConfig openConfig = CircuitBreakerConfig.custom()
                .slidingWindowSize(2)
                .minimumNumberOfCalls(2)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofHours(1))
                .build();
        CircuitBreaker openBreaker = CircuitBreaker.of("open", openConfig);

        // Two failures in a two-sample window transition the breaker to OPEN.
        for (int i = 0; i < 2; i++) {
            try {
                openBreaker.executeSupplier(() -> {
                    throw new IllegalStateException("simulated failure");
                });
            } catch (IllegalStateException ignored) {
                // Only force OPEN state during setup; not measured in the benchmark.
            }
        }

        openWithFallback = () -> {
            try {
                return openBreaker.executeSupplier(direct);
            } catch (CallNotPermittedException ignored) {
                return -1;
            }
        };
    }

    @Benchmark
    public Integer directCall() {
        return direct.get();
    }

    @Benchmark
    public Integer closedCircuitBreaker() {
        return closed.get();
    }

    @Benchmark
    public Integer openCircuitBreakerWithFallback() {
        return openWithFallback.get();
    }
}
```

This example uses `CircuitBreaker` directly to isolate library overhead. It does not measure Spring AOP proxies, factories, HTTP clients, Micrometer exporters, or networking. If your application uses the Spring Cloud factory or annotations, add a separate integration benchmark to measure the real call path. A long `waitDurationInOpenState` prevents the breaker from leaving `OPEN` during the benchmark run.

Run benchmarks with multiple forks and warm-up iterations as shown, holding the JVM, CPU, and JDK constant. You can enable JMH allocation/GC profilers to inspect memory cost. Do not compare a single short run across two different machines or JVM configurations and draw conclusions about overhead.

## 6. Load Testing with k6 at Fixed Offered Load

For end-to-end systems, use a load generator that maintains a steady request rate. Example k6 script using the `constant-arrival-rate` executor:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_load: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 200),
      timeUnit: '1s',
      duration: __ENV.DURATION || '5m',
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
};

export default function () {
  const baseUrl = __ENV.BASE_URL;
  const response = http.get(`${baseUrl}/api/inventory/SKU-42`, {
    tags: { scenario: __ENV.SCENARIO || 'closed' },
  });

  check(response, {
    'server returned an HTTP response': (r) => r.status > 0,
  });
}
```

Run each scenario as a separate execution, for example:

```bash
k6 run -e BASE_URL=http://localhost:8080 -e SCENARIO=closed -e RATE=200 -e DURATION=5m circuit-breaker.js
```

Before each run, put the stub and breaker into the desired state. For the `OPEN` scenario, wait until the state is open before starting k6. Record `http_req_duration`, `http_reqs`, `http_req_failed`, status codes, and `dropped_iterations`. If `dropped_iterations` rises, the generator failed to deliver the full offered load; do not interpret server throughput as if it received the full request rate.

A constant arrival rate keeps offered load relatively steady when responses slow down. In scenarios with expected failures, explicitly define which fallback responses are acceptable under the API contract. Do not ignore 5xx responses merely to make test pass rates green; keep status codes for SLI and service-error analysis.

## 7. Step-by-Step Execution Procedure

To keep results comparable, use the same duration and load across runs:

1. **Prepare:** fix the application version, JDK, JVM flags, CPU/memory limits, instance count, HTTP client config, and payload. Confirm Prometheus scraping and stub metrics are active.
2. **Warm up:** run light load and ramp up until JIT, connection pools, and caches stabilize. Exclude the warm-up phase from main measurements.
3. **Baseline:** run the direct call path with a healthy dependency. Record throughput, latency, CPU/request, GC, and stub request count.
4. **Healthy CLOSED:** enable the Circuit Breaker, keep the dependency healthy, and send the same offered load. The delta against baseline is the normal-path overhead.
5. **CLOSED with latency:** add realistic latency in the stub. Verify that breaker overhead is not confused with network and dependency processing time.
6. **Continuous failures:** make the stub return 5xx or time out. Measure time from the first failure until the breaker becomes `OPEN`, requests sent during that phase, and fallback cost.
7. **Steady OPEN:** continue the same offered load while the breaker is open. Measure rejection latency, CPU, fallback cost, and confirm stub request counts stop rising from blocked calls.
8. **HALF_OPEN / recovery:** switch the stub back to success after the open duration. Record probe counts, latency, and time until the breaker stabilizes in `CLOSED`.
9. **Repeat:** run each scenario at least three times or until variance settles; rotate scenario order if possible to reduce effects from CPU thermals, caches, and background noise.

Choose a steady-state duration long enough to collect enough samples for p95/p99. Under lower traffic, run longer to obtain reliable percentiles. Use identical offered load rather than just identical virtual-user counts when comparing throughput under fixed load.

## 8. Computing Overhead and Comparing Results

Under the same offered load and environment, compute the latency delta:

```text
latency_overhead_ms = p95_closed_ms - p95_baseline_ms

relative_latency_overhead_pct =
    (p95_closed_ms - p95_baseline_ms) / p95_baseline_ms * 100
```

For example, if baseline p95 is 40 ms and `CLOSED` p95 is 41 ms, the delta is 1 ms, or 2.5%. This is an arithmetic example, not an expected overhead number for Resilience4j.

For CPU, compare CPU-seconds per completed request instead of raw total CPU when throughput differs. For throughput, compare completed requests per second at the same offered load and valid-response ratio. When an `OPEN` scenario returns HTTP 200 fallbacks, separate fallback responses from requests served successfully by the dependency.

Compare at least these outcomes:

| Scenario | API p95/p99 | CPU/request | Dependency Request Rate | Fallback / Rejection |
| --- | --- | --- | --- | --- |
| Baseline | Reference point | Reference point | Roughly equal to offered load | No breaker rejections |
| Healthy CLOSED | Normal-path overhead | Sample recording cost | Roughly equal to offered load | Low or zero |
| Continuous failures | Shifts during detection phase | Error/logging/metrics cost | Drops after circuit opens | Rises with errors and rejections |
| Steady OPEN | Rejection + fallback time | Local handling cost | Near zero for blocked calls | Rejections/fallbacks increase |
| HALF_OPEN | May fluctuate from probes | Probe and transition cost | Only a few probes sent | Depends on recovery outcomes |

Never judge by average latency alone. A configuration with a good average can still breach SLOs if p99 spikes sharply. Read percentiles alongside throughput, dropped iterations, status codes, and resource usage.

## 9. Analyzing the Three States from a Performance Perspective

### CLOSED — Cost on the Success Path

In `CLOSED`, every outcome must be recorded into the sliding window. Overhead can come from state synchronization, window statistics updates, timing measurements, metric tags, and aspects/proxies if annotations are used. Window size and `COUNT_BASED`/`TIME_BASED` mode can affect memory and processing cost; benchmark with production-like settings.

If JMH shows small library overhead while load tests show elevated p99, inspect proxies, logging, metrics exporters, thread contention, and connection pools. Do not blame the Circuit Breaker for the entire delta simply because it was just enabled.

### Continuous Failures — Cost Before and During Opening

A breaker cannot know a dependency is broken before receiving error or slow outcomes. Initially, requests still reach the dependency until `minimumNumberOfCalls` is met and the error rate crosses the threshold. That duration depends on request rate, dependency latency, and the sliding window.

When failures are timeouts, waiting requests can continue holding threads and connections until client or `TimeLimiter` timeouts expire. Opening the Circuit Breaker does not automatically free every in-flight task. Measure in-flight requests, waiting threads, leased connections, and the time from first error until resources are released.

### OPEN — The Fast-Rejection Path

In `OPEN`, the Circuit Breaker rejects new requests with `CallNotPermittedException` before calling the dependency. This path usually has lower latency than waiting on connect or read timeouts, yet total latency still includes fallbacks, caches, serialization, and writing the client response.

Verify via the stub's request counter: once the breaker is steadily open, requests from blocked paths must stop increasing. If they still rise, another call path may bypass the breaker, use a different breaker ID, or correspond to requests dispatched before the circuit opened.

### HALF_OPEN — Bounded Probe Load

After the open duration, the breaker admits the configured number of probes. When multiple application instances each hold their own breaker, each instance can run its own probes; aggregate probe load across the system can exceed the per-instance setting. When evaluating recovery load, factor in both instance count and breaker ID count.

Do not raise `permittedNumberOfCallsInHalfOpenState` solely to speed up recovery if the dependency cannot yet handle that load. The goal is to gather enough recovery signal with a small, controlled volume of requests.

## 10. Avoiding Benchmark Bias

- **JIT and warm-up:** the JVM needs warm-up time for hot compilation; skipping warm-up inflates initial run metrics.
- **Coordinated omission:** models that send a new request only after the previous one finishes hide latency when the server slows down. Use fixed offered load when evaluating capacity.
- **Saturated load generator:** monitor the generator's CPU, memory, and dropped iterations; run it on a dedicated host whenever possible.
- **Connection pools:** keep pool size, keep-alive, and timeouts identical between baseline and breaker runs.
- **GC and caches:** record GC pauses, heap usage, and warm vs. cold cache state; never mix different cache states.
- **Logs and metrics:** keep exporter and logging configuration identical across comparisons; if measuring their overhead, vary one factor in a dedicated run.
- **Concurrency:** keep instance count, threads, and offered load fixed. In WebFlux, never compare a healthy event-loop run against a run with blocking calls on the event loop.
- **Circuit Breaker state:** confirm the state before measuring each phase; do not blend `CLOSED`, transition, and `OPEN` samples into a single percentile.
- **Response semantics:** separate HTTP 2xx fallbacks, 503, 504, and connection errors; do not treat every HTTP response with a status code as healthy fulfillment.

## 11. Evaluation Criteria and Decision Rules

Define acceptance criteria before running tests to avoid cherry-picking favorable runs:

- `CLOSED` p95/p99 overhead stays within the API latency budget.
- CPU-seconds/request and allocations/request stay within the resource budget.
- Throughput at target offered load does not drop noticeably beyond SLO tolerance.
- Under continuous failures, the breaker opens within the expected sample count and time; requests generated during detection remain within backend tolerance.
- When `OPEN`, the dependency receives no new requests from the protected path, and fallbacks meet SLAs.
- When `HALF_OPEN`, aggregate probes across all instances do not overload the recovering dependency.
- No queues, threads, or connections remain held well past timeouts beyond design limits.

If `CLOSED` overhead is high, inspect configurable factors first: metrics, logging, sliding window size, contention, proxies, and invocation style. If the `OPEN` path is slow, profile fallback/cache and serialization separately. If continuous failures exhaust threads, check timeouts and Bulkheads; opening a Circuit Breaker alone does not abort requests already in flight.

## 12. Result Reporting Template

Record every run along with metadata so tests can be reproduced:

| Field | Values to Record |
| --- | --- |
| Build | Git revision, Spring Boot, Spring Cloud, Resilience4j, JDK |
| Runtime | CPU/memory limits, JVM flags, instance count, container/VM |
| Workload | Offered rate, concurrency, payload, duration, warm-up |
| Dependency | Stub mode, latency, error rate, timeouts, and connection pool |
| Circuit Breaker | Window type/size, minimum calls, threshold, wait duration, half-open permits |
| Results | Throughput, p50/p95/p99, error ratio, CPU/request, GC, threads/queues |
| Protection | Time to OPEN, dependency request count, not-permitted count, fallbacks, probe count |

Never publish a single overhead number without configuration, load, hardware, versions, and measurement methodology. Reports should include both the median across runs and run-to-run variance.

## References

- [Resilience4j – CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): sliding window, minimum calls, failure threshold, and states.
- [Resilience4j – Micrometer](https://resilience4j.readme.io/docs/micrometer): Circuit Breaker metrics and call observation.
- [OpenJDK JMH](https://github.com/openjdk/jmh): JVM benchmarking framework, warm-up, forks, measurement, and profilers.
- [Grafana k6 – Constant arrival rate executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): generating offered load at a fixed request rate.
- [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, HTTP server metrics, and histograms.

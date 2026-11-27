# Throughput, Latency Percentiles, and Identical Test Load

When comparing Spring Boot on the JVM against an application compiled into a **GraalVM Native Image**, a claim such as "native is faster" is meaningful only when both versions receive the exact same load and are measured under equivalent conditions. You must inspect **throughput**, **latency percentiles**, error rates, and resource consumption together. A single average number can hide slow requests or periods when the system failed to keep up with the target load.

In the **`SPRING_BOOT_NATIVE_IMAGE`** module, the goal is to compile applications with Spring AOT, evaluate startup and memory, run compatibility tests, package containers, and operate native builds. This lesson establishes a repeatable benchmarking workflow: defining the workload, locking data and environment, selecting an appropriate load model, measuring RPS alongside p50/p95/p99, locating saturation points, and building an interpretable JVM/native comparison table.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish throughput, offered load, completed requests, and successful throughput.
- Read p50, p95, and p99 and understand why tail latency matters.
- Choose an open workload model or a closed workload model based on the measurement objective.
- Design identical request mix, data, duration, and load configuration for JVM/native.
- Use k6 `constant-arrival-rate` to keep iteration start rates stable.
- Track `http_req_duration`, `http_req_waiting`, `http_req_failed`, and `dropped_iterations`.
- Separate warm-up time from the steady-state measurement window.
- Measure CPU, RSS/container memory, and GC alongside latency/throughput.
- Identify the maximum load that still satisfies SLOs.

## 2. Three Metric Groups to Measure

An HTTP service benchmark requires at least three metric groups:

| Group | Metrics | Question to Answer |
|---|---|---|
| Throughput | Offered requests/s, completed requests/s, successful requests/s | How many requests per second does the system receive and process? |
| Latency | p50, p90, p95, p99, sometimes p99.9 | How long do users wait, especially in the tail of the distribution? |
| Reliability | HTTP error rate, business failure rate, timeouts, dropped iterations | Does the system process correctly and sustain the offered load? |

You should also record CPU, RSS/container working set, heap, GC pauses, thread/connection pools, and database utilization. These metrics help explain why throughput or latency changes.

### 2.1. Throughput and RPS

**Throughput** is the amount of work completed per unit time. For HTTP APIs, requests per second (RPS) is standard:

\[
\text{RPS} = \frac{\text{completed requests in measurement window}}{\text{seconds in measurement window}}
\]

Distinguish three values:

- **Offered load:** the rate at which the load generator attempts to start requests/iterations.
- **Completed throughput:** the number of requests receiving a complete response per second.
- **Successful throughput:** the number of requests completing and meeting business validation per second.

If a test targets 100 iterations/s but only 85 iterations/s complete, the system has not proven it can serve 100 requests/s. When each iteration sends one HTTP request, iteration rate roughly equals request rate. When one iteration calls three endpoints, request rate may be nearly triple the iteration rate.

Do not divide successful requests by a total duration that includes warm-up, ramp-up, or teardown if your measurement window is steady-state only. Use the exact interval during which the target load was held steady.

### 2.2. Latency and Percentiles

Latency is the duration from when the client sends a request until it receives a response according to the chosen metric definition. Rather than looking only at the average, examine the distribution:

| Percentile | How to Read |
|---|---|
| p50 | 50% of requests have latency less than or equal to this value; near the median |
| p90 | 90% of requests are no slower than this value |
| p95 | 95% of requests are no slower than this value; the remaining 5% are slower |
| p99 | 99% of requests are no slower than this value; the remaining 1% lie in the tail |
| p99.9 | Observes the extreme tail; requires far more samples for stable interpretation |

Illustrative example: p95 = 250 ms means 95 out of 100 requests had latency at or below 250 ms in the sample distribution; roughly the remaining 5% were slower. If p50 is 80 ms while p99 is 1.8 s, most requests are fast yet a small group of users still waits a long time.

Average can be useful for total processing cost, but it is easily skewed by outliers and cannot describe the tail. Never declare a service meets SLOs based on average alone.

### 2.3. Percentiles Need Sufficient Samples

p99 marks the slowest 1% of the distribution. With 100 samples, the top 1% corresponds to roughly a single observation; p99 is then highly sensitive to individual requests. Generate thousands or more requests within the measurement window depending on the stability required, and report sample counts alongside percentiles.

Do not sum or average p95 numbers across multiple runs and call the result an overall p95. Keep per-run results; you may report the median and range of per-run p95 values. If pooling raw samples, ensure every run used the exact same metric definition and load distribution.

## 3. Choosing the Right Load Model

Load generators can drive load by virtual user (VU) count or by request/iteration arrival rate. Two common models are the **closed model** and the **open model**.

### 3.1. Closed Model: Fixed Concurrent Users

In a closed model, a VU starts its next iteration only after the previous iteration finishes. If the server slows down, the VU waits longer and automatically reduces the rate of new iterations.

This model fits when simulating a fixed group of concurrent users performing actions with think time, such as 200 employees interacting with a UI. However, when the goal is verifying whether a service sustains a fixed arrival rate, a closed model causes offered load to drop as server latency rises. This phenomenon is commonly known as **coordinated omission**.

### 3.2. Open Model: Arrival Rate Independent of Response Time

In an open model, new iterations are scheduled according to the configured arrival rate without waiting for prior iterations to complete. When responses slow down, the system keeps receiving new iterations until the load generator's VU limit is reached.

This model fits when answering: "Can the service sustain 100 requests/s for 5 minutes?" k6 supports the open model via `constant-arrival-rate` and `ramping-arrival-rate`.

| Benchmark Goal | Appropriate Model |
|---|---|
| Keep 100 iterations starting per second | Open model, `constant-arrival-rate` |
| Ramp from 50 to 200 iterations starting per second | Open model, `ramping-arrival-rate` |
| Simulate 100 active users waiting for each response before the next action | Closed model, `constant-vus` |
| Simulate user sessions with think time | Closed model, fixed VUs and deliberate sleep/think time |

No single model fits every question. Choose according to the production behavior you want to emulate and state it clearly in the report.

## 4. Defining the Workload Before Measuring

"Identical test load" means both versions receive the same workload under a documented contract. Lock down at minimum:

1. **Request mix:** ratio of GET/POST/PUT, endpoints, message types, or business flows.
2. **Payload:** JSON size, file uploads, record counts, and data types.
3. **Identity:** identical authentication type, JWT claims/roles, and tenant distribution.
4. **Data:** identical dataset, row counts, indexes, transaction state, and cache state.
5. **Arrival rate:** identical ramp schedule and rate at every step.
6. **Duration:** identical warm-up, ramp-up, steady-state window, and cooldown.
7. **Connections:** identical HTTP version, TLS, keep-alive, connection reuse, and network path.
8. **Dependencies:** identical database, cache, message broker, and external services.

For example, an API workload might look like:

| Request Group | Illustrative Weight | Data |
|---|---:|---|
| Catalog read | 60% | Same set of product IDs |
| Order read | 20% | Same set of order IDs and statuses |
| Order creation | 15% | Identical payload and idempotency rules |
| Report read | 5% | Same filters and date ranges |

These percentages are illustrative only. Derive the request mix from production telemetry or well-defined use cases. If a heavy endpoint is omitted from the benchmark, results will not represent the real workload.

### 4.1. Lock Data and System State

Native and JVM must start from equivalent data states:

- Restore the same database snapshot or seed dataset.
- Delete or reset test-created records between runs.
- Decide explicitly on warm cache vs. cold cache; never let one version enjoy a warm cache while the other does not.
- Keep indexes, schemas, connection pools, and database configuration unchanged.
- Use identical JWT claims, user roles, tenants, and permissions.
- If the test writes data, use unique IDs or reset the database so later runs do not hit a different workload.

A GET test against a warm cache cannot be fairly compared against a run forced to query the database. Likewise, do not let the JVM benefit from caches populated by a prior benchmark run while native starts with an empty cache.

### 4.2. Lock the Request Sequence When High Repeatability Is Needed

If a workload mixes multiple request types, use the same script and data files for both binaries. When exact sequence reproducibility is required, use a fixed request schedule or deterministically seeded data rather than letting two runs pick different random inputs.

When relying solely on random weights, two runs can have slightly different counts per request type. That can still work for high-level benchmarks if ratios are large and variance is small, though you should measure latency per endpoint/tag to detect skew.

## 5. Keeping JVM and Native Image Environments Equivalent

Runtime differences are part of the comparison; unintended environmental differences invalidate conclusions. Record the following for each run:

| Component | What to Keep Identical or Record |
|---|---|
| Host | Same CPU model, core count, architecture, kernel, and load generator machine |
| Container | Same CPU quota, memory limit, replica count, and network mode |
| Application | Same commit, Spring Boot/Spring Framework versions, dependencies, and endpoint logic |
| Database/cache | Same version, configuration, dataset, and network placement |
| Connection pool | Same min/max pool size, timeouts, and connection reuse |
| HTTP | Same HTTP/1.1 or HTTP/2, TLS, keep-alive, and payloads |
| Security | Same auth flow, token validation, claim mapping, and authorization rules |
| Runtime tuning | Explicitly record JVM heap/GC flags and Native Image GC/heap/build options |

Place the load generator on a dedicated machine or verify it has ample spare CPU and network capacity. If k6 saturates CPU or bandwidth, results will reflect load generator limits rather than the application.

### 5.1. Comparing CPU and Memory Properly

Do not compare only the Java heap against the Native Image heap. RSS/container working set also includes code, metaspace/code cache (JVM), native allocations, thread stacks, runtime structures, and other memory regions. Native Image and HotSpot organize memory differently.

Collect:

- Container memory working set/RSS and peak RSS.
- Heap used/committed and GC metrics from the respective runtime.
- CPU usage at both container and host levels.
- GC count, pause time, and allocation rate where available.
- Thread count, connection pool usage, and queue depth.

Apply identical memory limits and CPU quotas to compare behavior under the same resource budget. Specific tuning flags for JVM or Native Image can differ; document them rather than pretending both runtimes share identical internal defaults.

## 6. Warm-Up and Steady-State

The HotSpot JVM needs time for the JIT to compile hot methods. Native Image compiles code ahead of time and lacks the same HotSpot JIT process, yet can still fluctuate while the application builds connection pools, populates caches, initializes clients, loads data, and warms databases/caches.

Separate two questions accordingly:

- **Cold start:** from process launch until the application is ready to accept traffic.
- **Steady-state performance:** throughput, latency, and resource usage after the application stabilizes.

Do not fold startup time into steady-state request latency. Neither should you measure the JVM right after startup and compare it to a stabilized native instance.

### Recommended Warm-Up Workflow

1. Launch the binary and wait for the readiness probe to succeed.
2. Send a predefined warm-up workload, identical for both runtimes.
3. Exclude warm-up data from the steady-state measurement window.
4. Start the measurement window once latency, CPU, and connection pools stabilize.
5. Sustain target load for the same duration, e.g., 5 minutes.
6. Collect metrics and archive logs from both the application and the load generator.

An experimental setup might use 60–120 seconds of warm-up followed by 5 minutes of steady-state; actual duration depends on the application and stabilization time. If there are multiple caches or background tasks, define clearly when the system is considered stable.

## 7. Creating a k6 Script with Constant Arrival Rate

The following example schedules 100 iterations per second for 5 minutes. Each iteration sends one HTTP GET request, so the configured arrival rate closely matches the offered request rate.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';
import { Counter, Rate } from 'k6/metrics';

const baseUrl = __ENV.BASE_URL || 'http://127.0.0.1:8080';
const successfulRequests = new Counter('successful_requests');
const businessSuccess = new Rate('business_success');

export const options = {
  discardResponseBodies: true,
  scenarios: {
    steady_load: {
      executor: 'constant-arrival-rate',
      rate: 100,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 80,
      maxVUs: 300,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<250', 'p(99)<750'],
    http_req_failed: ['rate<0.01'],
    business_success: ['rate>0.99'],
    dropped_iterations: ['count==0'],
  },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
  const response = http.get(baseUrl + '/api/catalog', {
    tags: { name: 'GET /api/catalog' },
  });

  const ok = check(response, {
    'status is 200': (res) => res.status === 200,
  });

  businessSuccess.add(ok);
  if (ok) {
    successfulRequests.add(1);
  }
}
~~~

The p95, p99, and success-rate thresholds in the example are illustrative values only. Replace them with your service's SLOs. `discardResponseBodies` reduces memory overhead when tests only inspect status codes; if you need to validate payloads, omit this option or re-enable response bodies for specific requests.

Run on Linux/macOS:

~~~bash
BASE_URL=http://127.0.0.1:8080 k6 run benchmark.js
~~~

On PowerShell:

~~~powershell
$env:BASE_URL = "http://127.0.0.1:8080"
k6 run benchmark.js
~~~

To compare, run the same script sequentially against the base URL or port of JVM and native. Keep rate, duration, thresholds, data, and dependent services unchanged.

### 7.1. Understanding Arrival Rate Configuration

| Option | Meaning |
|---|---|
| `rate` | Number of iterations to start per `timeUnit` |
| `timeUnit` | Time interval used to calculate rate |
| `duration` | Duration to sustain the arrival rate |
| `preAllocatedVUs` | Number of VUs initialized before starting |
| `maxVUs` | Maximum VUs k6 is permitted to allocate |

With one request per iteration, `rate: 100` and `timeUnit: '1s'` means k6 attempts to start about 100 iterations/requests per second. Actual rate can fall lower if there are insufficient VUs to execute iterations or the load generator is constrained.

Do not add `sleep()` at the end of an iteration when using an arrival-rate executor. The executor already paces iteration starts according to `rate` and `timeUnit`.

## 8. Ensuring the Load Generator Has Enough VUs

Each iteration requires a free VU. When requests slow down, more iterations stay in flight simultaneously and more VUs are needed to sustain the arrival rate.

Initial estimate:

\[
\text{Required VUs} \approx \text{arrival rate} \times \text{iteration duration (seconds)}
\]

For instance, 100 iterations/s with ~0.2-second iteration duration requires roughly 20 active VUs, plus margin for jitter. This is only an estimate; verify active VUs and `dropped_iterations` in practice.

If no free VU is available, k6 cannot start the iteration on schedule and increments `dropped_iterations`. Possible causes include:

- `preAllocatedVUs` or `maxVUs` set too low.
- Iterations taking longer because the SUT slowed down.
- Load generator running out of CPU or memory to spawn more VUs.
- Test script doing heavy local work beyond HTTP requests.

Increasing VUs only solves capacity shortages on the load generator. If the SUT is already saturated, raising `maxVUs` piles more load onto the server and drives latency/errors up sharply; document that as a stress test outcome.

A valid comparison run must have `dropped_iterations` equal to 0 or within a defined error budget. If one run has many dropped iterations, you cannot claim both builds received the same offered load.

## 9. Reading k6 HTTP Metrics

k6 provides built-in metrics:

| Metric | Meaning |
|---|---|
| `http_reqs` | Total HTTP requests executed |
| `http_req_duration` | Time spent sending + waiting for response + receiving response body |
| `http_req_waiting` | Time waiting for response, commonly used as TTFB |
| `http_req_connecting` | Time spent establishing TCP connection |
| `http_req_tls_handshaking` | Time spent in TLS handshake |
| `http_req_blocked` | Time waiting for a connection slot before sending |
| `http_req_failed` | Rate of requests marked as failed |
| `dropped_iterations` | Number of iterations that could not start on schedule |

`http_req_duration` excludes DNS lookup, connection slot waiting, TCP connect, and initial TLS handshaking. Those phases have separate metrics. Consequently:

- Use `http_req_duration` to compare server/response-path request time when connections are already established.
- Use `http_req_waiting` to observe time to first byte (TTFB).
- Inspect `http_req_connecting` and `http_req_tls_handshaking` if the benchmark involves fresh connections or TLS setup.
- Keep keep-alive/connection reuse consistent when focusing on request-processing cost.

`http_req_failed` reflects k6's response callback rules; it does not understand all business errors. For example, an HTTP 200 carrying a business status REJECTED may still count as an HTTP success. Use `check()` and custom `Rate`/`Counter` metrics to measure business success separately.

## 10. Measuring a Request Mix Instead of a Single Endpoint

The script above illustrates a single endpoint. For a representative benchmark, extend the same script to invoke the full defined request mix. You can use `group()` to separate metrics by flow or tag requests with stable names:

The snippet below extends the previous script and reuses the `baseUrl` variable declared there.

~~~javascript
import { group } from 'k6';
import http from 'k6/http';

export default function () {
  group('catalog-read', () => {
    http.get(baseUrl + '/api/catalog', {
      tags: { name: 'GET /api/catalog' },
    });
  });

  group('order-read', () => {
    http.get(baseUrl + '/api/orders/ORDER-100', {
      tags: { name: 'GET /api/orders/{id}' },
    });
  });
}
~~~

This only demonstrates grouping and metric naming; in a real test, adjust call counts/ratios to match your target workload. If each iteration calls two endpoints, `rate` represents workflows started per second, not HTTP requests per second.

Always inspect percentiles per endpoint or business group. An aggregate workload p95 can be dominated by a high-volume endpoint and mask a rare yet very slow endpoint.

## 11. Defining Measurement Windows and Repeating Benchmarks

A steady-state procedure can follow these steps:

1. Start databases, caches, message brokers, and dependencies.
2. Start exactly one application variant; wait for readiness.
3. Run the warm-up workload at the defined rate and request mix.
4. Start the fixed measurement window, e.g., 5 minutes at 100 iterations/s.
5. Save the k6 summary, metrics time series, application metrics, and container metrics.
6. Stop the application and reset data if the test performs writes.
7. Run the other variant under identical conditions.
8. Repeat each variant multiple times; alternate JVM/native ordering across iterations to reduce time-of-day bias.

Do not run JVM and native simultaneously on the same host if they contend for CPU, memory, or database connections when the goal is comparing each binary individually. If you need to test combined capacity when running side by side, treat that as a separate workload and report it separately.

### Number of Runs

A single run can be skewed by system noise, GC, background jobs, or network hiccups. Perform at least several stable repetitions; save every run and report median/range for throughput, p95, p99, and error rate.

If runs fluctuate widely, find the root cause before concluding. Never discard a run merely because it produced unfavorable numbers; exclude a run only for documented technical reasons such as load generator failure, dependency restart, or an interrupted test.

## 12. Building a JVM and Native Image Results Table

Use a consistent table per run:

| Metric | Spring Boot JVM | Spring Boot Native | Conditions |
|---|---:|---:|---|
| Offered load (iterations/s) | Record result | Record result | Same rate |
| Completed HTTP RPS | Record result | Record result | Same measurement window |
| Successful RPS | Record result | Record result | Same business checks |
| p50 latency | Record result | Record result | Same metric/endpoint |
| p95 latency | Record result | Record result | Same metric/endpoint |
| p99 latency | Record result | Record result | Same metric/endpoint |
| HTTP failure rate | Record result | Record result | Same response rules |
| Dropped iterations | Record result | Record result | Should equal 0 |
| Avg/peak CPU | Record result | Record result | Same CPU quota |
| Peak RSS/working set | Record result | Record result | Same memory limit |

When reporting, always include:

- Number of requests/samples in the measurement window.
- Code revision, Spring Boot, JDK/GraalVM versions, and build flags.
- Container size, CPU/memory limits, and replica count.
- Database/cache versions, dataset, and cache state.
- k6 version, script revision, rate, duration, and VU allocation.
- Any excluded runs along with reasons.

### Interpretation Examples

Suppose both builds receive the full 100 requests/s with zero dropped iterations:

- Native has lower p50 yet higher p99: most requests are faster, but the tail may be worse; check GC, queueing, database, or outliers.
- Native has lower p95 yet lower successful RPS: completed request latency looks better, yet more requests may be failing or incomplete; you cannot conclude it is better.
- Native uses less RSS yet higher CPU: memory footprint drops at the cost of higher CPU; evaluate against deployment goals and resource budgets.
- JVM p99 spikes when CPU hits its limit: it may have entered saturation; inspect thread pools, queues, GC, and dependencies.

Never declare one runtime an overall winner based on a single improved metric.

## 13. Finding the Saturation Point and Sustainable Throughput

Benchmarks should not test only a single rate. Step load upward incrementally—for example 25, 50, 75, 100, 125, and 150 iterations/s—keeping request mix and step duration identical.

At each step, record:

- Offered arrival rate and completed/successful RPS.
- p50, p95, p99.
- Error rate and dropped iterations.
- CPU, RSS, GC, queue depth, and database utilization.

Saturation typically appears when raising offered load barely increases completed throughput while tail latency, errors, or queues climb rapidly. **Sustainable throughput** is the highest load that still satisfies SLOs and error budgets over a sufficiently long measurement window.

~~~mermaid
flowchart LR
    A["Increase offered load"] --> B["Throughput rises"]
    B --> C["Reach saturation zone"]
    C --> D["Throughput plateaus"]
    D --> E["p95/p99 and errors spike"]
    E --> F["Identify sustainable rate within SLO"]
~~~

Do not treat the peak rate a server briefly survived for a few seconds as production capacity. Production capacity must hold over a representative duration with headroom for traffic bursts, background jobs, and dependency variance.

## 14. Separating Startup Benchmarks from Throughput Benchmarks

Startup time and steady-state throughput are two separate benchmarks:

| Benchmark | Start/End Points | What to Control |
|---|---|---|
| Cold startup | Process start to readiness/health endpoint ready | Fresh process, dependencies ready, identical readiness definition |
| First request | First request to first response | Caches, connections, and lazy initialization |
| Steady-state throughput | After warm-up, inside steady load window | Identical offered load, request mix, and duration |
| Steady-state memory | After warm-up and during steady window | RSS/working set, heap, and GC |

Measure cold startup across multiple fresh process launches. Do not run a single startup and claim stability. For JVM, distinguish app-ready time from JIT warm-up time; for native, distinguish app-ready time from cache/connection stabilization time.

## 15. PGO and Runtime Tuning Are Separate Variants

Native Image supports Profile-Guided Optimization (PGO). PGO uses profiles captured from a representative workload to guide compiler optimizations at build time. It can be a valuable variant when throughput is the target, provided the profile comes from an appropriate workload and is managed as part of the build.

When evaluating:

1. Benchmark the default native binary first.
2. If testing PGO, generate the profile using a representative workload with a production-like request mix.
3. Build the PGO binary separately and document profile/build flags.
4. Rerun the exact benchmark used for JVM and default native.
5. Report PGO as a distinct variant rather than merging it with default native results.

Similarly, if you change GC, heap maximum, optimization level, target CPU architecture (`-march`), or container resource limits, create a separate benchmark configuration. Such changes can improve one metric while altering memory, tail latency, or hardware compatibility.

## 16. Mistakes That Invalidate Benchmarks

| Mistake | Consequence | Fix |
|---|---|---|
| Comparing two different request mixes | Throughput/latency are no longer comparable | Use the same script, data, and endpoint weights |
| Looking only at average latency | Hides tail latency | Report p50, p95, p99, and sample count |
| Using a closed model to prove fixed RPS | Arrival rate drops when the server slows down | Use an open model for fixed arrival rates |
| Ignoring dropped iterations | Assumes full load was sent even when the generator dropped iterations | Set thresholds and inspect the metric |
| Load generator runs out of CPU | Measures client limits instead of the server | Isolate the load generator and monitor its resources |
| Measuring JVM right after start and native after warm-up | Unfairly penalizes JVM for JIT/caches | Warm up both under the same rules |
| Different cache/database states | Results reflect data state instead of runtime | Reset/seed data and standardize warm/cold cache |
| One build has higher error rates | Sample latency may reflect only successful requests | Report error rate and successful throughput |
| Aggregating all endpoints into one percentile | Rare slow endpoints get masked | Tag and analyze per endpoint |
| Running only once | System noise decides the outcome | Repeat, save individual runs, and report variance |
| Changing flags between binaries without logging | Unclear whether differences stem from runtime or tuning | Document build/runtime configuration |

## 17. Repeatable Benchmark Workflow

~~~mermaid
flowchart TD
    A["Choose SLOs and benchmark questions"] --> B["Define request mix + dataset"]
    B --> C["Lock host/container/dependencies"]
    C --> D["Build JVM and Native from same code"]
    D --> E["Start and warm up"]
    E --> F["Run open-load at fixed rate"]
    F --> G["Collect throughput, percentiles, errors, CPU, RSS"]
    G --> H["Repeat and alternate runtime order"]
    H --> I["Step up rate to find saturation"]
    I --> J["Analyze sustainable throughput"]
    J --> K["Archive script, config, and report"]
~~~

Checklist:

- [ ] Defined SLOs for p95/p99, error rate, and throughput.
- [ ] Defined request mix, payload, authentication, and dataset.
- [ ] Selected open/closed model matching measurement goals.
- [ ] Used the same k6 script and request data for JVM/native.
- [ ] Separated the load generator from the application host.
- [ ] Locked CPU/memory quotas, replicas, and dependency versions.
- [ ] Specified warm-up and steady-state window before running.
- [ ] Tracked `http_req_duration`, `http_req_waiting`, `http_req_failed`.
- [ ] Tracked `http_reqs`, successful RPS, and `dropped_iterations`.
- [ ] Collected CPU, RSS/container memory, GC, and queue/pool metrics.
- [ ] Repeated the benchmark multiple times and archived each run.
- [ ] Analyzed latency per endpoint, not just aggregate percentiles.
- [ ] Stepped load up incrementally to find saturation and sustainable throughput.
- [ ] Recorded all build flags, GC settings, and PGO variants.

## 18. Self-Check Exercises

**Question 1.** What does p95 = 300 ms mean?

**Hint:** roughly 95% of requests in the sample had latency no greater than 300 ms; the remaining 5% were slower.

**Question 2.** Why is average latency insufficient to evaluate user experience?

**Hint:** average does not describe the tail; a cluster of very slow requests can be hidden.

**Question 3.** When you need to sustain an offered load of 100 requests/s, why consider `constant-arrival-rate`?

**Hint:** it is an open model where iteration starts are independent of the previous iteration's response time.

**Question 4.** How does `dropped_iterations` differ from `http_req_failed`?

**Hint:** a dropped iteration never started due to insufficient VUs or scheduling capacity; a failed request executed and was marked failed.

**Question 5.** Why can you not compare a JVM measured right after startup against a warmed-up native build?

**Hint:** the JVM undergoes JIT warm-up; both runtimes also have caches, connections, and initialization affecting results.

**Question 6.** If native has better p50 but worse p99, what else should you inspect?

**Hint:** queueing, CPU saturation, GC, database latency, thread/connection pools, and per-endpoint distributions.

**Question 7.** Why measure successful RPS alongside `http_reqs`?

**Hint:** request count may include error responses or business rejections; successful RPS reflects useful throughput.

## 19. References

- [Grafana k6 — Open and closed models](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/): differences between closed and open models, and coordinated omission.
- [Grafana k6 — Constant arrival rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): configuring arrival rate, duration, and VU allocation.
- [Grafana k6 — Dropped iterations](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/): causes and interpretation of `dropped_iterations`.
- [Grafana k6 — Built-in metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/): `http_req_duration`, `http_req_waiting`, `http_reqs`, errors, and other metrics.
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/): p95/p99 conditions and pass/fail test criteria.
- [GraalVM Native Image — Optimizations and Performance](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/): optimization levels, PGO, and throughput tuning options.
- [GraalVM Native Image — Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/): heap and garbage collectors in Native Image.

**Key takeaway:** A JVM/native comparison is valid only when both receive the same workload, the same data, and the same resource budget. Report throughput, successful RPS, p50/p95/p99, errors, and dropped iterations together; separate startup from steady-state; repeat runs; and find the highest load still meeting SLOs rather than picking the prettiest latency number.

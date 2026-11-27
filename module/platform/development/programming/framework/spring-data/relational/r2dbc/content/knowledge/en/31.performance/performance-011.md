# Realistic Load Testing and Avoiding the Assumption That Non-Blocking Is Always Faster

Spring Data R2DBC and Spring WebFlux enable reactive, non-blocking database access. This model helps applications serve many concurrent I/O-bound requests with fewer threads and better resource efficiency. However, **non-blocking does not mean individual requests run faster, SQL executes faster, or the system automatically achieves higher throughput than JDBC**.

Performance must be measured on production-like workloads. A query may take 20 ms in both JDBC and R2DBC; differences appear in thread counts needed for 1,000 concurrent requests, scheduler overhead, connection pools, serialization, or database saturation. Once the database becomes the bottleneck, switching to non-blocking does not make the database execute more SQL statements per second.

This lesson covers designing benchmarks, interpreting latency and throughput metrics, recognizing R2DBC limits, comparing fairly against JDBC, and avoiding conclusions drawn from tiny synthetic tests.

## 1. Non-Blocking Changes How I/O Waits, Not How Fast I/O Runs

In traditional blocking models, a thread is typically held while waiting for the database response:

~~~text
Request A -> Thread A -> send SQL -> wait on DB -> receive result -> return response
                                       |
                                       +-- Thread A stays occupied
~~~

With non-blocking reactive I/O, threads do not sit idle waiting in that way. While awaiting database data, the pipeline yields execution so the event loop can handle other work:

~~~text
Request A -> event loop -> send SQL -> register continuation on result
                                       |
                                       +-- event loop handles requests B/C

Database response -> resume pipeline A -> return response
~~~

The primary gain lies in efficient thread and resource utilization across many concurrent I/O waits. Database SQL execution time still depends on query plans, indexes, locks, CPU, disk, network, and database load.

### 1.1. Three Concepts Not to Equate

| Concept | Question It Answers |
| --- | --- |
| Latency | How long does a single request take from start to finish? |
| Throughput | How many requests or transactions does the system complete per unit of time? |
| Resource efficiency | To achieve that throughput/latency, how much CPU, memory, threads, connections, and network does it consume? |

Non-blocking can improve resource efficiency or high-concurrency scalability without lowering single-query latency. Conversely, reactive pipeline overhead can make a simple low-load path slightly slower than straightforward blocking code.

### 1.2. A Faster Query Does Not Equal a Faster System

Suppose two implementations return an identical order list:

- JDBC: p50 latency 18 ms, p95 45 ms.
- R2DBC: p50 latency 19 ms, p95 43 ms.

These numbers are practically tied. If R2DBC uses substantially fewer threads at 1,000 concurrent requests, it offers scalability and resource advantages. Yet you cannot claim R2DBC makes queries faster from those p50/p95 figures.

Another benchmark might favor blocking when queries are ultra-short, load is light, and reactive pipeline overhead represents a larger share of total work.

## 2. Measuring the Right Metrics

Do not look solely at averages or raw requests per second. A performance report should include at least:

- **Throughput:** completed requests/second or transactions/second.
- **Latency percentiles:** p50, p90, p95, p99, and p99.9 when needed.
- **Error rate:** timeouts, HTTP 5xx, database errors, connection acquire timeouts, and rejected requests.
- **Concurrency:** active in-flight requests and queued requests.
- **Resource usage:** CPU, heap, garbage collection, threads, connections, network, and I/O.
- **Database health:** CPU, memory, disk IOPS, lock waits, active sessions, query latency, and slow queries.

### 2.1. Why p95 and p99 Matter

Averages hide small groups of very slow requests. Suppose 99 requests take 20 ms while 1 request takes 2 seconds. The 100-request average still looks low, yet users hitting that slow request suffer poor experience.

Meaningful percentiles:

- p50: half of requests are faster than or equal to this value.
- p95: 95% of requests are faster than or equal to this value.
- p99: 99% of requests are faster than or equal to this value.

For interactive APIs, p95/p99 reveal tail latency far better than averages. Collect proper histograms or detailed samples; never compute fleet-wide percentiles by averaging percentiles from individual instances.

### 2.2. Throughput Must Be Paired with Error Rate

A system can report high throughput by failing fast or rejecting requests. Count only successful requests when measuring business capacity.

Example:

| Outcome | Requests/second |
| --- | ---: |
| Total requests received | 1,000 |
| Succeeded | 820 |
| Timed out or errored | 180 |

Reporting 1,000 requests/second misleads stakeholders into thinking the system successfully serves 1,000 requests per second.

### 2.3. Measuring Latency at the Right Boundaries

An end-to-end API flow includes:

1. Receiving and authenticating the request.
2. Parsing/validating the request.
3. Waiting for a pool connection.
4. Sending SQL and awaiting the database.
5. Mapping rows to entities/DTOs.
6. Calling dependent services.
7. Serializing and sending the HTTP response.

Measuring only repository query time misses connection acquisition, serialization, and downstream calls. Measuring only HTTP latency hides which layer is the bottleneck.

Collect both end-to-end metrics and per-component metrics. Distributed tracing or observation helps break down time, though instrumentation adds overhead and must stay consistent across comparisons.

## 3. Designing Production-Like Workloads

A benchmark has value only when its workload reflects real usage. Specify:

- Read/write mix and query types.
- Request/response payload sizes.
- Row counts read or updated.
- Tenant, user, and key access distributions.
- Cache hit/miss ratios.
- Transactions and statements per transaction.
- Concurrent arrivals and arrival rates.
- Burst frequency and sustained load durations.
- External HTTP/messaging dependencies, if any.

### 3.1. Do Not Benchmark Only a Trivial SELECT

Example repository query:

~~~java
public Mono<Customer> findById(Long id) {
    return customerRepository.findById(id);
}
~~~

This benchmarks a useful primitive, yet does not represent real production endpoints that check permissions, filter by tenant, join tables, paginate, map DTOs, write audits, or invoke other services.

Maintain small micro-benchmarks to understand component costs alongside end-to-end benchmarks to evaluate realistic behavior.

### 3.2. Use Representative Data Distributions

A 100-row table fits easily in cache and tells nothing about production tables with tens of millions of rows. Benchmark datasets should match:

- Total rows and index sizes.
- Duplicate value ratios.
- Hot-key vs. cold-key distributions.
- Payload sizes.
- Filter selectivity ratios.
- Data skew between small and large tenants.

If production includes a few massive tenants, testing only tiny tenants misses index, query-plan, and noisy-neighbor issues.

### 3.3. Keep Queries and Semantics Equivalent When Comparing

When comparing JDBC against R2DBC, both implementations must do identical work:

- Identical SQL or equivalent query logic.
- Identical schema, indexes, data, and database instance.
- Identical transaction boundaries and isolation levels.
- Identical row counts and returned payloads.
- Identical mapping, validation, and business rules.
- Identical timeouts, retries, and connection limits.
- Identical cache and network conditions.

If one side selects a single column while the other maps a full entity graph, the comparison is unfair.

## 4. Load Models: Closed Workload vs. Open Workload

How load is generated strongly shapes benchmark results.

### 4.1. Closed Workload

A closed workload maintains a fixed pool of virtual users. Each user sends a request, waits for a response, pauses briefly, and sends the next request.

~~~text
User 1: request -> wait response -> think -> request -> ...
User 2: request -> wait response -> think -> request -> ...
...
User N: request -> wait response -> think -> request -> ...
~~~

When the server slows down, sending rate drops automatically because virtual users block awaiting responses. This masks overload: a slowing server throttles the load generator.

Closed workloads suit interactive user flows with think time, yet fail to model traffic arriving at a constant rate independent of server latency.

### 4.2. Open Workload

An open workload injects requests at a scheduled arrival rate, e.g., 200 requests/second, regardless of whether prior responses finished.

~~~text
Arrival schedule: 200 requests/second
       |
       +--> request A waiting
       +--> request B waiting
       +--> request C starts
       +--> request D starts
~~~

This model reveals what traffic rate the system sustains before latency, queues, and errors climb sharply. When the server falls behind, in-flight requests or required virtual users grow.

### 4.3. Coordinated Omission

Load generators that wait for one request to finish before scheduling the next slow down whenever the server stalls, omitting the requests that should have arrived during that stall.

This skews latency histograms artificially low because un-sent requests during slowdowns never appear in measurements.

To measure capacity and tail latency under steady incoming traffic, prefer open/constant-arrival-rate workloads and monitor dropped iterations or missed schedules. Never look only at latencies of completed requests.

## 5. Little's Law and the Relationship Between Concurrency, Throughput, and Latency

Little's Law describes steady-state relationships:

\[
L = \lambda W
\]

Where:

- \(L\): average number of requests in the system.
- \(\lambda\): average throughput, requests per second.
- \(W\): average time a request spends in the system, in seconds.

For example, if a system completes 200 requests/second at an average latency of 0.1 seconds:

\[
L = 200 \times 0.1 = 20
\]

Roughly 20 requests are active or queued in the system on average.

Little's Law estimates required concurrency rather than predicting peak throughput. Near saturation, queueing delays rise rapidly and steady-state assumptions break down.

### 5.1. Raising Concurrency Does Not Always Raise Throughput

As concurrent requests climb:

1. The database receives more work.
2. Idle CPU or I/O gets utilized better initially.
3. Past a threshold, the database saturates.
4. New requests wait on connections, locks, or CPU.
5. Latency climbs sharply while throughput plateaus.

That is why benchmarks must locate the saturation point instead of pushing concurrency to maximum.

## 6. Connection Pools Are Part of the Measurement

R2DBC typically uses connection pools to reuse connections. Pool sizing affects concurrent statements, connection wait times, active database sessions, database load, and socket resources.

Bigger pools are not automatically better. If a database handles 80 concurrent queries efficiently, opening 500 connections drives up lock contention, context switching, and memory pressure.

### 6.1. Separating Pool Wait from Query Latency

A request taking 150 ms might break down as:

| Stage | Time |
| --- | ---: |
| Waiting to acquire connection | 90 ms |
| Database executing query | 35 ms |
| Mapping and remaining overhead | 25 ms |

Looking only at total latency blames SQL when most time was actually spent waiting on the connection pool.

Track:

- Acquired/active connections.
- Idle connections.
- Pending acquire requests.
- Acquire latency and timeouts.
- Pool max size.
- Connection hold time.

Exact metric names depend on pool, Spring Boot, and Micrometer integration versions.

### 6.2. Summing Connections Across Multiple Instances

Across multiple application replicas, effective connection load is the sum across all replicas:

\[
\text{Potential connections}
= \text{replicas} \times \text{pool max size}
\]

For 6 replicas with max pool size 30 each:

\[
6 \times 30 = 180
\]

The database must tolerate around 180 application connections alongside workers, migrations, monitoring, and admin tools. Budget connections system-wide.

### 6.3. Pool Exhaustion

When all connections stay pinned, new requests queue. Common causes:

- Pool undersized for workload.
- Long-running queries or transactions.
- Publishers pinning connections while awaiting HTTP services.
- Very slow `Flux` consumers keeping result streams open.
- Blocking or synchronous logic inside transactions.
- Connection leaks from improper lifecycle/subscription handling.

Never increase pool size immediately upon seeing acquire timeouts. First measure connection hold times, query latency, and database saturation to locate root causes.

## 7. Backpressure and Data Consumption Speed

Reactive Streams support backpressure: downstream signals how many elements it is ready to handle, throttling producers that honor demand when consumers slow down.

Example:

~~~java
public Flux<OrderSummary> streamOrders(Long customerId) {
    return orderRepository.findAllByCustomerId(customerId)
            .map(OrderSummary::from);
}
~~~

When downstream consumes slowly, backpressure can throttle emission for demand-aware publishers. However, backpressure neither speeds up SQL execution nor eliminates every buffer/queue in the system.

### 7.1. `collectList` Can Negate Streaming Benefits

~~~java
return orderRepository.findAllByStatus("OPEN")
        .collectList()
        .map(this::buildResponse);
~~~

`collectList` retains all elements in memory before emitting. On large datasets, heap climbs and GC drives tail latency.

For large lists, favor pagination, result caps, or appropriate streaming responses. Streaming carries its own cost: connections and cursors stay held while clients read.

### 7.2. Bounding Concurrency in `flatMap`

~~~java
return orderRepository.findAllByStatus("READY")
        .flatMap(order -> inventoryClient.check(order.getId()), 16);
~~~

The concurrency argument caps active inner publishers in this step. Avoid cranking concurrency up blindly to chase throughput; downstream services or connection pools can overload.

Benchmark across multiple concurrency settings while monitoring latency, pending work, error rates, and resource usage.

### 7.3. Fetch Size and Streaming Depend on the Driver

Batched fetching, cursors, and buffering vary by R2DBC driver and database. When reading large result sets, measure rows per fetch, memory growth across result sizes, connection hold times, slow-consumer impact, and cancellation behavior on client disconnect.

Never assume all drivers share identical fetch-size behavior merely because the code uses `Flux<T>`.

## 8. Threads and Schedulers in Reactive Applications

WebFlux typically runs on an event loop. Event-loop threads must return promptly to serve many concurrent connections and requests.

### 8.1. Blocking Calls Break the Non-Blocking Model

Avoid blocking calls on event loops:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return Mono.fromCallable(() -> blockingCustomerClient.fetch(id));
}
~~~

This still blocks whichever thread runs the callable. `Mono` does not magically turn blocking APIs into non-blocking ones.

When legacy blocking libraries cannot be replaced yet, isolate them onto an appropriate scheduler:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return Mono.fromCallable(() -> blockingCustomerClient.fetch(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

This isolates blocking work rather than making it non-blocking. Bounded schedulers have resource limits and must be monitored.

### 8.2. Do Not Offload Everything to `boundedElastic`

Non-blocking R2DBC drivers do not need every repository call wrapped in `subscribeOn(boundedElastic())`. Doing so adds queue/scheduler overhead and negates event-loop efficiency.

Reserve scheduler hops for actual needs such as legacy blocking APIs, blocking file I/O, non-reactive libraries, or CPU-bound work requiring dedicated schedulers.

### 8.3. CPU-Bound Work Still Needs CPU

Reactive pipelines still burn CPU for large JSON parsing, encryption, calculations, or compression regardless of non-blocking I/O.

Once CPU saturates, adding request concurrency slows things down. Profile CPU, reduce work, optimize algorithms, or scale CPU capacity.

## 9. Designing Fair R2DBC vs. JDBC Benchmarks

Comparing two stacks requires isolating variables. Changing driver, pool, SQL, schema, threads, and serialization simultaneously obscures what caused any difference.

### 9.1. Keep Environments Equivalent

| Factor | How to Keep Fair |
| --- | --- |
| Database | Same instance or identically spec'd environment |
| Schema/indexes | Identical migrations and equivalent execution plans |
| Dataset | Identical row counts and data distributions |
| Queries | Identical SQL or equivalent query logic |
| Transactions | Identical isolation and boundaries |
| Pools | Document max connections and timeout settings on both sides |
| Application | Identical CPU/memory limits and replica counts |
| Responses | Identical payloads and serialization |
| Load | Identical arrival rates, durations, and scenarios |
| Caches | Identical warm/cold cache policies |

JDBC and R2DBC configurations need not match parameter-for-parameter where threading models differ, yet differences must be documented and tested under equivalent resource budgets.

### 9.2. Comparing at Two Levels

**Microbenchmarks** measure isolated Java functions, converters, or small mappings; JMH fits controlled CPU/micro-operation benchmarks.

**End-to-end benchmarks** measure real HTTP requests through application, pool, driver, and database—these govern production API evaluation.

Never extrapolate from a converter microbenchmark to claim R2DBC beats JDBC on database workloads.

### 9.3. Verify Query Plans Before Comparing Drivers

If both implementations run identical SQL yet one draws a different query plan due to statistics, parameterization, or cache warmth, results do not isolate driver differences.

Check plans via database tools like `EXPLAIN` or `EXPLAIN ANALYZE`. Confirm indexes are used properly without unexpected full scans or abnormal lock waits.

## 10. Reliable Load-Testing Workflow

A test suite should include these stages:

1. **Preparation:** seed data, run migrations, configure pools, verify database health.
2. **Warm-up:** ramp load gradually so JVM JIT, connection pools, and caches stabilize.
3. **Baseline:** test light load to verify latency and correctness.
4. **Steady load:** hold a fixed arrival rate long enough to observe steady-state behavior.
5. **Step load:** step traffic upward to locate where latency/errors spike.
6. **Stress:** push past capacity in a controlled test to observe degradation behavior.
7. **Soak:** sustain load over an extended window to catch leaks, pool exhaustion, or memory drift.
8. **Recovery:** drop load and verify the system recovers cleanly.

Exclude warm-up intervals from primary metrics. Repeat runs and record run-to-run variance.

### 10.1. Example k6 Script with Constant Arrival Rate

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_api_load: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 500,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<250', 'p(99)<500'],
  },
};

export default function () {
  const response = http.get('http://localhost:8080/api/orders?limit=20');
  check(response, {
    'status is 200': (res) => res.status === 200,
  });
}
~~~

Rates, durations, and thresholds here are purely illustrative. Substitute real SLOs and traffic profiles. Watch dropped iterations and active virtual users; if the generator fails to sustain the target arrival rate, results understate offered load.

### 10.2. Stepping Load in Stages

Example test matrix:

| Stage | Arrival Rate | Duration | Goal |
| --- | ---: | ---: | --- |
| Warm-up | 20 req/s | 2 min | Warm JVM and pools |
| Step 1 | 50 req/s | 3 min | Baseline |
| Step 2 | 100 req/s | 3 min | Moderate load |
| Step 3 | 200 req/s | 5 min | Target load |
| Step 4 | 300 req/s | 5 min | Locate saturation |
| Soak | 150 req/s | 30 min | Watch for drift/leaks |

Never reuse identical figures across unrelated systems. Tailor steps to expected traffic, SLOs, database capacity, and environment limits.

## 11. Correlating Application, Reactor, and Database Metrics

HTTP stats alone cannot explain why a system slows down. Place metrics side by side on the same timeline.

### 11.1. Application Metrics

- CPU utilization and throttling.
- Heap usage, allocation rates, and GC pauses.
- Thread counts and thread states.
- Event-loop utilization and lag.
- Scheduler queues and rejected tasks.
- HTTP request latency, throughput, and error rates.
- Serialization time where measurable.
- Active in-flight requests.

### 11.2. Connection Pool Metrics

- Active/acquired connections.
- Idle connections.
- Pending acquires.
- Acquire latency.
- Acquire timeouts.
- Connection hold times.
- Pool max size and created connection counts.

### 11.3. Database Metrics

- CPU, memory, and disk I/O.
- Active sessions and running queries.
- Lock waits and deadlocks.
- Slow queries and execution plans.
- Buffer/cache hit ratios.
- Connection counts and churn.
- Transaction durations and rollback rates.

Low app CPU paired with high pool pending points toward the database or pool. High event-loop lag alongside fast database queries points toward blocking calls or CPU-heavy tasks on the event loop.

### 11.4. Selective Micrometer and Observation Usage

Spring Boot and Micrometer provide HTTP, JVM, and configurable database/pool metrics. Observations and tracing follow requests across components.

Enable necessary metrics rather than collecting everything; enable histograms for percentile timers; avoid high-cardinality tags like tenant ID, user ID, or request ID; rely on traces and logs to inspect single requests instead of per-request metric labels; and keep instrumentation identical when comparing JDBC vs. R2DBC.

Observability consumes CPU, memory, and network bandwidth. Document instrumentation settings inside benchmark reports.

## 12. Recognizing Common Bottleneck Types

### 12.1. Database Saturation

Symptoms:

- High database CPU or I/O.
- Rising query latency.
- Rising active sessions and lock waits.
- Throughput stalls despite rising arrival rates.

Fixes: optimize execution plans and indexes, reduce round trips, shrink rows read/written, tighten transactions and locks, throttle concurrency and pools, or scale the database/add read replicas where appropriate.

Switching from JDBC to R2DBC never fixes a bad query plan.

### 12.2. Connection Pool Saturation

Symptoms:

- Rising pending acquires.
- Acquire latency dominating request latency.
- Database still shows spare capacity or lower-than-expected active sessions.
- Requests timing out before SQL starts.

Fixes: locate publishers holding connections too long, shorten transactions, move HTTP calls outside database transactions, tune pools within database limits, and verify totals across all replicas.

### 12.3. Blocked Event Loop

Symptoms:

- Rising event-loop lag.
- Rising HTTP latency even when database queries remain fast.
- Thread dumps showing event-loop threads blocked on I/O or monitors.
- CPU may look low or high depending on the blocking operation.

Fixes: remove `block()`, JDBC, or blocking clients from event loops, isolate legacy blocking code on proper schedulers, and profile CPU and lock contention. Tools like BlockHound can catch unexpected blocking calls in test suites.

BlockHound finds executed violations; it does not prove all code paths are non-blocking. Test critical paths and inspect real drivers/clients.

### 12.4. CPU-Bound Mapping and Serialization

Symptoms:

- High application CPU.
- Fast database queries.
- Large responses or heavy mapping.
- Rising GC and allocations.

Fixes: trim returned columns, use lean projections/DTOs, avoid `collectList` on huge sets, optimize serializers and algorithms, and offload CPU-heavy work to appropriate schedulers when justified by measurements.

### 12.5. Downstream Tail Latency

An endpoint may query the database quickly yet stall on slow external services. p50 looks healthy while p99 spikes whenever downstream hiccups.

Measure each dependency separately, set realistic timeouts, bound concurrency, and design business fallbacks. Non-blocking prevents holding threads while waiting without eliminating dependency latency.

## 13. When Can R2DBC Be Slower?

Situations where R2DBC may not outperform JDBC:

- Light load with low concurrency and tiny queries, where reactive pipeline overhead dominates.
- Heavy mapping or CPU-expensive converters.
- Excessive unnecessary operators or context propagation.
- Drivers or features less optimized for the workload.
- Undersized connection pools or misconfigured acquire timeouts.
- Pipelines spawning excessive inner publishers or over-high concurrency.
- Blocking calls accidentally running on event-loop threads.
- Saturated databases where freeing application threads cannot raise throughput.

Conversely, JDBC with thread-per-request or virtual threads can serve many workloads cleanly. Choose architectures from system goals rather than reactive vs. non-reactive labels.

### 13.1. Reactive Overhead Exists

Reactive pipelines incur publisher/subscriber allocation, context propagation, operator fusion/boundaries, scheduler hops when present, per-item mapping, and backpressure coordination.

Reactor optimizes heavily, yet costs remain non-zero. Do not sprinkle `publishOn`/`subscribeOn` everywhere without reason and metrics.

### 13.2. Non-Blocking Does Not Mean Zero Threads

Applications still run threads for event loops, database drivers, schedulers, callbacks, and background tasks. The advantage is avoiding pinning one dedicated thread per in-flight I/O wait as traditional blocking does—not running threadless.

## 14. Anti-Patterns That Skew Benchmarks

| Anti-Pattern | Why It Misleads or Slows Code | Fix |
| --- | --- | --- |
| Measuring only average latency | Hides tail latency | Report p50/p95/p99 and histograms |
| Benchmarking 1 sequential request | Generates no production-like concurrency | Run concurrent workloads |
| Using closed workloads for continuous traffic | Slow server throttles load generator | Use open arrival-rate scenarios |
| Benchmarking on empty/tiny databases | Fails to reflect indexes, caches, or skew | Seed production-like datasets |
| Testing only a trivial SELECT | Skips auth, mapping, transactions, and dependencies | Pair microbenchmarks with end-to-end tests |
| Comparing different queries | Fails to isolate variables | Keep SQL and semantics equivalent |
| Maximizing pool size | Can overload the database | Measure pool waits and DB headroom |
| Calling `collectList` on huge results | Inflates memory and GC | Paginate or use bounded streaming |
| Blocking on the event loop | Stalls unrelated requests | Use non-blocking clients or isolate blocking calls |
| Adding schedulers on every operator | Adds queue and context-switch overhead | Switch schedulers only when needed |
| Skipping JVM warm-up | Measures JIT compilation and cold pool setup | Warm up before measurement windows |
| Running only once | Vulnerable to environmental noise | Repeat runs and report variance |
| Ignoring errors or dropped iterations | Artificially inflates throughput or lowers latency | Track errors and dropped work |
| Ignoring database metrics | Blames drivers for database bottlenecks | Collect DB metrics on the same timeline |
| Running load generator on an overloaded host | Generator bottlenecks the test | Isolate generator and verify spare capacity |

## 15. Example: Reading Benchmark Results

Suppose two implementations run at 200 requests/second against the same database and payload:

| Metric | JDBC | R2DBC |
| --- | ---: | ---: |
| Successful throughput | 198 req/s | 199 req/s |
| p50 | 24 ms | 25 ms |
| p95 | 61 ms | 60 ms |
| p99 | 120 ms | 118 ms |
| Error rate | 0.2% | 0.1% |
| Application threads | 220 | 48 |
| Application CPU | 52% | 49% |
| Database CPU | 68% | 69% |

These are hypothetical figures illustrating interpretation, not universal results.

Valid conclusions:

- Latency and throughput are nearly identical on this workload.
- R2DBC used fewer application threads under this configuration.
- Database CPU barely changed, matching the identical SQL workload.
- There is no evidence R2DBC makes individual queries faster.
- If reducing thread/resource usage at high concurrency matters, R2DBC shows promise; test further at higher load and in soak tests.

Never conclude R2DBC is universally faster, because workload, driver, pool, hardware, and tuning can reverse outcomes.

### 15.1. When Throughput Rises While p99 Degrades

Suppose arrival rate increases from 200 to 350 req/s:

| Metric | 200 req/s | 350 req/s |
| --- | ---: | ---: |
| Successful throughput | 199 req/s | 320 req/s |
| p95 | 60 ms | 240 ms |
| p99 | 118 ms | 1,100 ms |
| Error rate | 0.1% | 4.5% |
| Pool pending | Low | High |

Throughput climbed yet the system approached or exceeded capacity. p99 and error rate surged; never rely on higher RPS alone to declare the higher-load configuration acceptable.

## 16. Setting SLOs and Capacity Targets

Benchmarks should answer concrete operational questions, such as:

- Can the system serve 250 req/s with p95 under 200 ms?
- At 500 req/s, does error rate stay below 0.5%?
- How much CPU, memory, and connections does each replica need?
- When a dependency slows by 2x, how does the API degrade?
- Does the system recover after spikes without restarts?

SLOs should specify latency percentiles and thresholds, error budgets/rates, minimum throughput, endpoint scope, and measurement windows.

Capacity targets need headroom. Never run continuously right on the saturation knee if traffic bursts or other workloads share the database.

## 17. Testing Resilience and Recovery

Beyond steady-state load, include these scenarios:

### 17.1. Spike Tests

Abruptly surge traffic briefly. Observe how quickly pool pending rises, whether queues accumulate, whether errors/timeouts spike, and whether latency returns to baseline afterward.

### 17.2. Soak Tests

Hold steady load for extended durations to uncover unreturned connections, creeping heap growth, growing scheduler queues, bloated caches, lengthening transactions, and gradual latency drift.

### 17.3. Dependency Degradation

Simulate slow databases, slow connection acquires, or lagging external services. Verify timeouts, concurrency caps, retries, and backpressure behave as designed.

Never configure unbounded retries on writes. Retries pile extra load onto struggling dependencies.

### 17.4. Recovery Tests

Once dependencies recover, verify pending queues drain, pools reuse connections normally, error rates normalize, and fresh requests are not dragged down by stale backlogs.

## 18. Using BlockHound to Detect Blocking Calls

BlockHound detects certain blocking calls executed on threads marked non-blocking, such as Reactor event loops. Integrate it in tests:

~~~java
@BeforeAll
static void installBlockHound() {
    BlockHound.install();
}
~~~

Then exercise critical code paths to catch blocking violations. Depending on library versions, allow-lists for known safe calls or integration plugins may be needed.

BlockHound catches violations along executed test paths. It does not prove the whole app is non-blocking, measure throughput, or replace load testing.

## 19. Writing Reproducible Benchmark Reports

Record for every run:

| Category | Details |
| --- | --- |
| Build | Commit, Java, Spring Boot, Spring Data, Reactor, and driver versions |
| Runtime | CPU/memory limits, JVM flags, replica counts |
| Database | Version, configuration, schema, indexes, and dataset |
| Pool | Pool type, max size, timeouts, and replica count |
| Workload | Scenario, arrival rate, concurrency, duration, and request mix |
| Observability | Enabled metrics/tracing and sampling rate |
| Results | Throughput, p50/p95/p99, errors, CPU, heap, threads, pool, and DB |
| Notes | Warm-up, cache state, environmental noise, and anomalies |

When comparing runs, keep code and configurations consistent. Whenever pool settings or queries change between runs, document them so driver effects are never confused with tuning changes.

### 19.1. Do Not Cherry-Pick the Best Run

If you run five benchmarks and report only the fastest, results are biased. Report all runs or medians/ranges and explain variance.

If sharing infrastructure with noisy neighbors, measure and note interference. When results sit close together, there may be insufficient evidence to declare either implementation faster.

## 20. Investigation Workflow When R2DBC Misses Targets

1. Confirm the load generator actually emits the intended arrival rate.
2. Check successful requests, error rates, and dropped work.
3. Compare p50/p95/p99 by endpoint and by dependency.
4. Inspect pending acquires and connection hold times.
5. Inspect database CPU, query plans, locks, and I/O.
6. Inspect application CPU, GC, threads, and event-loop lag.
7. Search for blocking calls or CPU-heavy work inside reactive pipelines.
8. Check returned row counts, `collectList`, pagination, and downstream demand.
9. Change one variable at a time and re-run the identical workload.
10. Record outcomes and verify gains do not worsen error rates or tail latency.

Never change pool size, concurrency, and replica count together and claim you found the root cause. Changing one variable at a time establishes clear cause and effect.

## 21. Questions to Answer Before Drawing Conclusions

- Does the workload match production?
- Was arrival rate decoupled from response latency?
- Did the load generator have spare capacity?
- Were JVM and pools warmed up?
- Were p95/p99 and error rates measured?
- Were pool waits and database metrics collected?
- Were SQL, indexes, data, and transactions equivalent in comparisons?
- Were any blocking calls running on event loops?
- Did throughput improve while tail latency stayed within SLO?
- Are results repeatable across multiple runs?

If major questions remain unanswered, treat conclusions as hypotheses needing further measurement.

## 22. Conclusion

Non-blocking is a resource-utilization model for awaiting I/O—not a promise that every database operation finishes faster. R2DBC helps applications handle high I/O concurrency with fewer threads, yet latency and throughput remain governed by queries, databases, connection pools, CPU, networks, mapping, and dependencies.

Measure throughput, p50/p95/p99, error rates, concurrency, application resources, pool waits, and database health together. Use production-like workloads, datasets, and transactions; pick open or closed models to match the question; warm up, step load, soak-test, and repeat runs. When comparing JDBC with R2DBC, keep SQL and semantics equivalent, control resources, and document configuration differences.

Strong conclusions tie directly to a concrete workload and target: how many successful requests per second the system sustains, at what tail latency and error rate, using what resources, and with how much headroom. No single benchmark proves non-blocking is universally faster than blocking across every application.

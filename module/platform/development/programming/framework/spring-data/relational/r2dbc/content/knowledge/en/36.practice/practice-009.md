# Load Testing, Identifying Bottlenecks, and Evaluating R2DBC

## 1. Why measure before choosing R2DBC?

R2DBC lets Java applications access databases using a reactive, non-blocking model. That helps a WebFlux application serve many concurrent I/O operations without tying up a dedicated thread while waiting on the database. However, R2DBC does not make SQL queries faster, does not increase database capacity, and does not guarantee higher throughput for every application migrated from JDBC.

A system can be slow for many reasons:

- Queries missing indexes or using poor execution plans.
- High database CPU, I/O, or lock contention.
- Exhausted connection pools or slow connection acquisition.
- Transactions holding connections for too long.
- Code invoking JDBC or blocking libraries on the event loop.
- Reactor pipelines spawning too many concurrent publishers.
- CPU-heavy serialization, mapping, or data processing.
- GC pauses, heap pressure, or network latency.
- Slow downstream services.
- An under-provisioned load generator.

Looking only at a single number such as requests/second or average response time leads teams to false conclusions. For instance, higher throughput paired with surging p99 latency may mean the system accepts more requests only by letting some requests queue for a long time. Or R2DBC may reduce thread counts while the database remains the bottleneck, leaving response times largely unchanged.

This lesson shows how to build repeatable benchmarks, trace bottlenecks from HTTP ingress to the database, and evaluate R2DBC on realistic workloads. Your findings should answer:

1. How much load can the current system sustain within SLOs?
2. Which resource saturates first?
3. How does R2DBC affect throughput, latency, concurrency, and resource cost?
4. Do gains come from the data access model or from changes to queries, pools, caches, or configuration?
5. Is R2DBC worthwhile for this workload and the current operations team?

## 2. Defining goals and SLOs before running load tests

A load test should not begin with "how many requests per second can it hit?". Start with user expectations and system limits to satisfy.

Example SLOs for an order-read API:

| Metric | Illustrative target |
|---|---:|
| Throughput at expected load | 500 requests/second |
| p95 latency | Under 200 ms |
| p99 latency | Under 500 ms |
| HTTP 5xx | Under 0.1% |
| Acquire timeouts | 0 under normal load |
| Database CPU | Below agreed operational threshold |
| Pool pending | Does not grow continuously |
| Memory | No unbounded growth during soak tests |

These numbers are illustrative only. Every application must set SLOs based on business requirements, deployment region, cost, and current baselines.

### 2.1. Distinguishing throughput and latency

- **Throughput** is work completed per unit of time, such as requests/second or transactions/second.
- **Latency** is the duration a single request takes to complete.
- **Concurrency** is the number of active requests or operations in flight simultaneously.
- **Error rate** is the fraction of failing requests.
- **Saturation** describes when a resource reaches its capacity limit or begins queuing.

These metrics relate to one another but are not interchangeable. A system can achieve high throughput with terrible latency, or low latency at low load before collapsing as concurrency rises.

### 2.2. Using percentiles instead of averages alone

Average latency hides tail latency. For example:

- 95 requests take 50 ms.
- 4 requests take 300 ms.
- 1 request takes 5 seconds.

The average may still look acceptable, yet users hitting the 5-second request suffer a poor experience.

Track at minimum:

- p50: typical median request in the distribution.
- p90: 90% of requests finish at or below this time.
- p95: tail behavior commonly targeted in SLOs.
- p99: exposes severely slow requests.
- Maximum: helpful when investigating, though sensitive to outliers and sample size.

Never sum segment percentiles to estimate end-to-end percentiles. Gateway p95 plus database p95 does not necessarily equal total request p95 because those percentiles may come from different requests. Measure end-to-end latency alongside individual spans.

### 2.3. Defining the error budget

If an SLO permits 0.1% errors, define clearly which failures count:
- HTTP 5xx.
- Timeouts.
- Connection acquire failures.
- Rate-limited rejections.
- Valid business rejections such as insufficient inventory.
- Client cancellations.

Do not lump valid business rejections into infrastructure errors if they mean different things. Conversely, do not omit timeouts and acquire failures from error rates merely because they didn't return 5xx.

## 3. Building a production-representative workload

A benchmark is only useful when the workload mirrors real-world usage.

Do not benchmark a single trivial primary-key lookup endpoint and generalize to the whole application. Real workloads mix multiple operation types in varying proportions.

Example profile for an order system:

| Use case | Share | Characteristics |
|---|---:|---|
| Get order by ID | 45% | Short query, indexed lookup |
| Search by status | 25% | Filtering, sorting, pagination |
| Create order | 10% | Insert and generated ID |
| Update status | 10% | Read-modify-write, transaction |
| Fetch history | 7% | Multi-row, time-sorted |
| Summary report | 3% | Heavy query, aggregation |

This is a hypothetical profile. Derive real ratios from anonymized access logs, traces, analytics, or product requirements.

### 3.1. Recording workload inputs

Capture:

- Number of users and tenants.
- Distribution of queried IDs.
- Cache hit/miss ratio.
- Typical and maximum page sizes.
- Hot vs. cold data ratio.
- Response payload sizes.
- Read/write ratio.
- Database operations per request.
- Transaction frequency.
- Error and retry rates.
- Downstream wait times.

A workload querying one hot ID behaves completely differently in CPU/DB caches than a workload spread evenly across millions of records.

### 3.2. Using sufficiently large, realistically distributed datasets

Too small a dataset fits entirely in memory/cache and fails to represent production. A large dataset with unrealistic skew can also mislead.

Consider:
- Row counts comparable to production.
- Production-matching indexes.
- Realistic status distributions.
- Tenant skew/distribution.
- `TEXT`/`BLOB` column sizes.
- Foreign keys and relationships.
- Share of frequently accessed hot rows.
- Concurrent update rates.

Benchmark data should be synthetic or anonymized. Never copy personal or sensitive production data into test environments without proper justification and safeguards.

### 3.3. Avoiding an all-cache-hit workload

If every iteration reads the same small working set already cached in RAM, you measure cache lookups rather than database capacity.

Maintain separate profiles:
- Hot data: most requests hit popular rows.
- Mixed: production-like distribution.
- Cold/wide: broader range scans.
- Write-heavy: frequent inserts and updates.
- Read-heavy: predominantly reads.
- Mixed transactional: multi-repository coordination inside transactions.

Never flush caches haphazardly between requests. Define explicitly whether a test measures warm-cache or cold-cache behavior and follow a repeatable procedure.

## 4. Choosing the load test type

Each test type answers a different question.

| Test type | Purpose | Example |
|---|---|---|
| Smoke | Verify system and scripts function | 1–5 users briefly |
| Load | Measure expected traffic | Sustain 500 RPS |
| Stress | Find breaking points and overload behavior | Ramp load until SLOs fail |
| Spike | Test sudden traffic bursts | Jump from 100 to 1,000 RPS in seconds |
| Soak | Detect leaks and long-term degradation | Sustain load for hours |
| Capacity | Find peak load meeting SLOs | Step up concurrency in stages |
| Scalability | Measure gains from added instances/resources | Add replicas or CPU |

Never substitute a stress test for a load test. A system might survive 2,000 RPS for a few seconds yet fail to sustain 500 RPS for an hour.

### 4.1. Load test

Run the workload at expected load and slightly above. The goal is validating SLOs, not breaking the system.

### 4.2. Stress test

Ramp load gradually to observe where things first degrade:
- p95/p99 breaches SLOs.
- Error rates climb.
- Pool pending acquires grow continuously.
- Database CPU or lock waits saturate.
- Event loops or app CPU hit limits.

Verify graceful degradation: early shedding, bounded timeouts, and no cascading collapse.

### 4.3. Spike test

Simulate marketing campaigns, batch jobs, or traffic surges. Observe whether pools open connections quickly enough, whether queues spike, and how long recovery takes after the burst subsides.

### 4.4. Soak test

Hold load steady over extended periods to expose:
- Steadily climbing memory usage.
- Connection leaks.
- Unreturned pool connections.
- Unbounded cache growth.
- Accumulating queues.
- Blocked threads or schedulers.
- Retry storms.
- Steadily growing database sessions.

## 5. Open workload model vs. closed workload model

How load is generated strongly shapes benchmark results.

### 5.1. Closed model

A closed model maintains a fixed number of virtual users. Each user sends a request, waits for the response, and only then sends the next request.

When the server slows down, the request rate automatically drops because virtual users are busy waiting. This masks overload: the slower the server gets, the fewer new requests the generator sends.

Closed models work well when simulating a bounded pool of concurrent users with think-time behavior.

### 5.2. Open model

An open model dispatches requests at a target arrival rate—such as 500 requests/second—regardless of whether prior requests have finished.

It tests whether the system sustains a given arrival rate. When the server slows down, in-flight requests pile up, exposing queueing and saturation.

Bound queues on the load generator and track dropped iterations. If the generator cannot sustain the target rate, results do not reflect the intended load.

### 5.3. Coordinated omission

If a load generator waits for one request to complete before scheduling the next, server stalls are under-represented in latency histograms. This phenomenon is known as coordinated omission.

Pick the appropriate workload model, use tooling with explicit arrival-rate measurement, and inspect dropped or delayed iterations.

### 5.4. Do not confuse virtual users with database concurrency

100 virtual users does not mean 100 concurrent database queries. A virtual user may:
- Pause for think-time.
- Call endpoints that do not touch the database.
- Hit cached responses.
- Run multiple queries sequentially.
- Hold a long-running request.

Measure request concurrency, active DB operations, and acquired pool connections separately.

## 6. Setting up a fair benchmark environment

To compare JDBC and R2DBC fairly, control all variables.

Keep identical:
- Hardware/VMs or CPU and memory limits.
- Database version and configuration.
- Dataset, schema, and indexes.
- Query semantics and returned results.
- Network path and TLS.
- Number of application replicas.
- JVM version and flags.
- Logging levels.
- Cache policies.
- Pool sizes and timeouts, within fair equivalents for each driver.
- Load generator and workload script.
- Warm-up duration.
- Measurement window and percentile calculation.

Document every configuration difference. Do not force JDBC and R2DBC into mismatched pool settings merely to match a raw integer, yet never give one implementation extra caching or different indexes.

### 6.1. Separate the load generator from the application host

If the load generator runs on the same machine as the application, they contend for CPU and network. As app load climbs, the generator slows down and skews results.

Best practices:
- Run the load generator on a dedicated host.
- Monitor generator CPU, memory, and network.
- Verify it actually hits the target request rate.
- Scale out multiple generators for heavy loads.
- Confirm the generator itself is never the bottleneck.

### 6.2. Keep the database isolated and observable

In benchmarks, give the database sufficient resources to distinguish app bottlenecks from database bottlenecks, while keeping realistic limits if production is constrained.

Monitor:
- CPU.
- Memory.
- Disk IOPS and latency.
- Active sessions.
- Running queries.
- Lock waits.
- Buffer/cache hit ratios.
- Replication lag if applicable.
- Connection rejections.

### 6.3. Warm-up and JIT

Java needs warm-up time for:
- Class loading.
- JIT compilation of hot paths.
- Connection pool initialization.
- Cache warming.
- Query plan/statement cache stabilization.
- Runtime profiling stabilization.

Never include the first few seconds after startup in primary results. Separate warm-up from the measurement window identically for both implementations.

### 6.4. Repeat runs and report variance

Run each scenario multiple times. Report medians or ranges across runs instead of cherry-picking the single best run.

When results fluctuate widely, investigate:
- Background jobs.
- Noisy neighbors.
- GC activity.
- Database checkpoints.
- Cache warmth.
- Network jitter.
- Load generator saturation.

A 2% improvement amidst 8% run-to-run variance is not reliable evidence.

## 7. Metrics to collect at every layer

You cannot pinpoint bottlenecks from application latency alone. Instrument the full path.

### 7.1. At the HTTP/API layer

Track:
- Request rate.
- In-flight requests.
- p50/p95/p99 latency.
- Status codes and error rates.
- Timeouts and cancellations.
- Request and response bytes.
- Latency per endpoint and use case.

If one endpoint lags behind others, break metrics down by route and request class rather than looking only at global aggregates.

### 7.2. At the JVM/application layer

Track:
- CPU utilization.
- Heap used and committed.
- Allocation rate.
- GC pauses and frequency.
- Thread counts.
- Thread states.
- Event-loop utilization and task queues.
- Scheduler queues if used.
- CPU profiling / JFR recordings.
- Serialization and mapping time.

R2DBC eliminates thread blocking while waiting on I/O, not CPU work. If mapping or JSON serialization is heavy, CPU remains the bottleneck.

### 7.3. At the connection pool layer

Track:
- Acquired connections.
- Allocated connections.
- Idle connections.
- Pending acquires.
- Acquire wait duration if available.
- Acquire timeouts and errors.
- Connection creation latency and failures.
- Configured pool max size and max pending.

High `acquired` does not equal active query count. Connections can sit idle inside transactions or while waiting on downstream calls.

### 7.4. At the database layer

Track:
- Query duration by query type.
- Execution plans.
- Rows scanned vs. returned.
- Active sessions and running queries.
- Lock waits and deadlocks.
- CPU, memory, and I/O.
- Connection limits.
- Transaction durations.
- Slow queries.
- Index usage.

High query latency under both JDBC and R2DBC points to SQL, indexes, database capacity, or the network rather than the data access API.

### 7.5. At the network and downstream layer

Track:
- TCP connections and retransmissions.
- Round-trip time (RTT).
- DNS/TLS handshake overhead if new connections open.
- Downstream p95/p99 latency.
- Retry rates.
- External API timeouts.
- Message broker latency.

If an R2DBC transaction holds a database connection while awaiting a downstream service, the pool can saturate even when the database is idle.

## 8. Measurement and observability tools

Combine these tool groups:

| Tool/group | Purpose |
|---|---|
| k6, Gatling, JMeter | Generate HTTP workloads |
| wrk/wrk2 or equivalents | Generate HTTP load and measure latency/throughput |
| Spring Boot Actuator | Expose health and application metrics |
| Micrometer | Instrumentation and metrics API |
| Prometheus + Grafana | Collect, query, and visualize time-series metrics |
| OpenTelemetry | Distributed tracing and context propagation |
| Java Flight Recorder (JFR) | Analyze CPU, allocations, locks, and runtime events |
| async-profiler | CPU and allocation profiling |
| Database EXPLAIN/EXPLAIN ANALYZE | Inspect query execution plans and costs |
| Database monitoring | Session, lock, I/O, and query statistics |

Do not turn on every heavy profiler simultaneously on every benchmark run. Heavy instrumentation perturbs measurements. Start with lightweight metrics, then run dedicated profiling once suspect areas emerge.

### 8.1. Metrics via Actuator/Micrometer

Example endpoint exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
~~~

With Prometheus registry enabled, scrape `/actuator/prometheus`. Exact meter names depend on instrumentation and versions; inspect the metrics endpoint to verify active meters.

### 8.2. Distributed tracing

Traces split requests into spans:
- HTTP server.
- Service logic.
- R2DBC query.
- Downstream HTTP.
- Message publishing.

When query spans are short yet service spans are long, delays live in application logic or downstream calls. When query spans dominate, inspect the database and execution plans.

Never record raw SQL containing sensitive values or bind parameters in traces. Use statement names, query fingerprints, or masked placeholders.

### 8.3. JFR and profiling

JFR helps pinpoint:
- Where threads block.
- CPU-hot methods.
- Allocation hotspots.
- GC pauses.
- Lock contention.
- Socket waits and thread scheduling.

In reactive applications, a raw stack trace may not show the full business flow because execution hops across callbacks and threads. Combine trace IDs, Reactor instrumentation, and profilers to connect segments.

## 9. Diagnosing bottlenecks from symptoms

The table below gives investigative leads, not automatic conclusions.

| Symptom | Likely bottleneck | Next check |
|---|---|---|
| High app CPU, low DB CPU | Mapping, serialization, business logic, or busy spin | CPU profile / JFR |
| Low app CPU, high DB CPU | Queries or database workload | Query plans, indexes, DB metrics |
| Acquired hits max, pending grows | Pool saturation or long-held connections | Transaction duration, acquire wait |
| Acquired low, pending still grows | Connection creation/validation/network or metric mismatch | Create failures, connect latency, pool config |
| Long query span, low app CPU | Database, locks, or network | EXPLAIN, lock waits, server query stats |
| Long service span, short query span | Logic, downstream calls, or queueing | Trace child spans |
| High p99 but healthy p50 | Tail latency, locks, GC, queues, or cold paths | Histograms, traces of slow outliers |
| Very high thread count in JDBC | Blocking concurrency / thread-per-request pressure | Thread dumps, thread states |
| Blocked event loop in WebFlux | Blocking call on an event-loop thread | BlockHound / JFR / thread dumps |
| Steadily growing memory in soak test | Leaks, unbounded buffers/queues/caches | Heap histograms, allocation profiles |
| DB sessions exceed pool allocation | Multiple instances/services or external connections | Total connection budget |
| Errors surge during spikes | Pools, queues, timeouts, or DB limits | Error types, pending, DB rejections |

### 9.1. Signs of a blocked event loop

WebFlux relies on a small pool of event-loop threads to multiplex many connections. One blocking call on an event-loop thread stalls unrelated requests sharing that thread.

Watch for:
- JDBC calls.
- `block()`, `blockFirst()`, `blockLast()`.
- `Thread.sleep`.
- Blocking file I/O.
- Synchronous SDKs.
- Long-held locks or `synchronized` blocks.
- CPU-heavy work not offloaded from the event loop.

Use BlockHound in development/tests to catch certain blocking calls on non-blocking threads. BlockHound does not replace profiling and cannot detect every bottleneck.

### 9.2. Signs of a database bottleneck

If adding application replicas fails to raise throughput while DB CPU or lock waits are already high, scaling app instances can make things worse.

Check:
- Execution plans.
- Missing or unused indexes.
- Query count per request.
- N+1 queries.
- Selecting unnecessary columns.
- Transaction and lock durations.
- Caching or read models where appropriate.

Switching JDBC to R2DBC never fixes a bad query plan.

### 9.3. Signs of a pool bottleneck

If pool pending acquires grow while the database still has spare capacity, inspect:
- Pool max size configured too low.
- Long transactions holding connections.
- Downstream calls inside transactions.
- Unclosed or slow-draining streams.
- Connection leaks.
- Slow connection validation or acquire timeouts.

Never raise pool limits before verifying how many sessions the database can actually handle. A pool is a queue protecting the database; opening more connections can simply shove saturation into the database.

## 10. Using Little's Law to reason about concurrency and queueing

Little's Law relates averages in a stable system:

\[
L = \lambda W
\]

Where:
- \(L\): average number of items in the system.
- \(\lambda\): average throughput (items/second).
- \(W\): average time an item spends in the system.

For example, if the system completes 200 requests/second with an average response time of 0.1 seconds:

\[
L = 200 \times 0.1 = 20
\]

On average, roughly 20 requests are in flight inside the system.

This estimates average request concurrency, not the exact pool limit or concurrent DB query count. One request may execute multiple queries sequentially or concurrently, while other requests skip the database altogether.

### 10.1. Queueing drives latency up sharply near saturation

As resource utilization nears 100%, wait times climb steeply. A pool running at 99% utilization is not necessarily better than one at 80% if p99 latency turns unstable.

Maintain adequate headroom for bursts, connection creation, maintenance, and competing workloads. Base headroom on production telemetry rather than a fixed rule-of-thumb ratio.

### 10.2. Do not apply Little's Law to the wrong scope

If throughput is HTTP RPS and \(W\) is HTTP latency, \(L\) is average in-flight HTTP requests—not database connections.

To estimate database connection concurrency, account for:
- Share of requests hitting the DB.
- Pool acquisitions per request.
- Connection hold time.
- Query parallelism per request.
- Number of pools and replicas.

## 11. Comparing JDBC and R2DBC fairly

The goal is not proving R2DBC is always faster. The goal is identifying which model fits your workload, SLOs, and operational costs.

### 11.1. Scenarios to compare

Benchmark at least:

1. Simple primary-key read.
2. Filtered, sorted, paginated read.
3. Multi-row / streaming query.
4. Simple insert.
5. Update with optimistic locking.
6. Multi-repository transaction.
7. Production-like mixed workload.
8. Burst and soak tests.

One implementation may outperform at high concurrency while showing zero difference at low load. Know which characteristics your system actually needs.

### 11.2. Keep query semantics identical

JDBC and R2DBC benchmarks must:
- Read identical datasets.
- Use identical filters and sorting.
- Return identical projections.
- Share equivalent transaction boundaries.
- Use identical indexes.
- Handle errors and retries equivalently.
- Enforce identical authorization.
- Avoid caching results on one side only.

If the R2DBC version also introduces a better SQL query, the benchmark conflates two changes. Separate benchmarks into:
- Driver comparison with equivalent SQL.
- End-to-end comparison of each option's tuned implementation.

Both measurements are valuable, but they answer different questions.

### 11.3. Never benchmark blocking JDBC directly on the event loop

JDBC must never run directly on WebFlux event-loop threads. When benchmarking JDBC inside WebFlux, offload blocking work onto an appropriate scheduler such as `boundedElastic` or a bounded executor tuned for the workload.

R2DBC executes on reactive pipelines. Document clearly:
- JDBC thread pool / scheduler.
- Worker thread count.
- Queue limits.
- JDBC connection pool settings.
- R2DBC connection pool settings.
- Request concurrency.
- Active database sessions.
- CPU and memory usage.

Giving JDBC an unbounded thread pool or R2DBC an oversized connection pool invalidates the comparison.

### 11.4. Compare resource efficiency, not just latency

R2DBC can keep fewer threads busy when many requests wait on I/O, yet it still consumes database connections and remains bounded by query and database limits.

Measure:
- Throughput within SLOs.
- p95/p99 latency.
- CPU per request.
- Memory and allocation rates.
- Thread counts.
- Context switches.
- Connection counts.
- Pool wait times.
- Database CPU.
- Code and operational complexity.

If R2DBC cuts thread counts without lowering latency, that still carries value for I/O-bound workloads hitting thread limits. Conversely, for small low-load apps where JDBC meets SLOs at lower operational cost, migrating may not pay off.

### 11.5. Match load levels and SLOs

Never compare:
- JDBC at 100 RPS against R2DBC at 1,000 RPS.
- Warm cache on one side vs. cold cache on the other.
- Connection pooling on one side vs. unpooled connections on the other.
- Transactions on one side vs. no transactions on the other.
- Returning 20 fields on one side vs. 3 fields on the other.

Build comparison tables across multiple load tiers and count throughput as valid only while error rates and latency remain inside SLOs.

## 12. Load generation example with k6

A simple script to test a search API:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    search_orders: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 300,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.001'],
    http_req_duration: ['p(95)<200', 'p(99)<500'],
  },
};

export default function () {
  const page = Math.floor(Math.random() * 10);
  const response = http.get(
    'https://test.example.com/orders?status=OPEN&page=' +
      page + '&size=20',
    {
      headers: {
        Authorization: 'Bearer ' + __ENV.TEST_TOKEN,
      },
      tags: {
        endpoint: 'order-search',
      },
    }
  );

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response has body': (r) => r.body && r.body.length > 0,
  });
}
~~~

This is an example script, not a universal configuration. Read tokens from test environment secrets rather than committing them to source control, and replace URLs and thresholds with your real endpoints and SLOs.

### 12.1. Reading k6 results

Inspect:
- `http_reqs`: total requests and effective rate.
- `http_req_duration`: HTTP request latency distribution.
- `http_req_failed`: failed request rate.
- `dropped_iterations`: scheduled iterations skipped because VUs or generator capacity ran out.
- `vus` and `vus_max`: virtual user utilization.

If `dropped_iterations` climbs, the generator could not sustain the target arrival rate. Never conclude the server handled the configured RPS if the generator dropped iterations.

### 12.2. Adding multiple scenarios

A more realistic script splits traffic across scenarios:
- Read by ID.
- Search.
- Create.
- Update.
- History.
- Report.

Match observed production ratios. For write scenarios, generate unique keys or reset fixtures cleanly so duplicate constraints and table growth do not skew runs.

## 13. Measuring performance at the database layer

### 13.1. Inspecting execution plans

For slow queries, run database `EXPLAIN`. In PostgreSQL, `EXPLAIN ANALYZE` executes the query and reports actual timings, so use it cautiously in test environments or on safe read queries.

Inspect:
- Sequential scan vs. index scan.
- Estimated rows vs. actual rows.
- Join strategy.
- Sort and hash operations.
- Rows removed by filter.
- Buffer hits vs. reads.
- Planning time and execution time.

Never tune pool sizes when a bad query plan is the real culprit.

### 13.2. Counting queries per request

A single request may call several repositories sequentially. If an endpoint triggers N+1 queries, request latency climbs even if each individual query is fast.

Track:
- Queries per request.
- Total database time per request.
- Query fingerprints.
- Rows scanned/read.
- Network round trips.
- Duplicate query rate.

Trim round trips with joins, projections, or batch fetches, without building giant queries that produce terrible plans or bloated payloads.

### 13.3. Checking transactions and locks

Long transactions hold locks that block competing requests. Monitor:
- Transaction age.
- Lock waits.
- Deadlocks.
- Idle-in-transaction sessions.
- Long-running queries.
- Commit and rollback latency.

R2DBC does not remove database locking semantics. Identical SQL at the same isolation level still obeys the engine's locking rules.

## 14. Step-by-step bottleneck investigation process

When a load test performs poorly, do not change multiple settings at once. Investigate layer by layer to isolate the limiting resource.

### Step 1: Verify the load generator

- Did it achieve the target arrival rate?
- Were any iterations dropped?
- Did generator CPU or network saturate?
- Did the generator have enough VUs and sockets?

### Step 2: Verify API behavior

- Did requests actually execute the intended use cases?
- Did validation or auth failures terminate requests prematurely?
- Were cache hit rates abnormally high?
- Were response sizes consistent across runs?

### Step 3: Inspect application resources

- Is app CPU high?
- Are heap usage or GC pauses abnormal?
- Is the event loop blocked?
- Are thread or scheduler queues growing?
- Are mapping or serialization consuming CPU?

### Step 4: Inspect the connection pool

- Is `acquired` hitting max?
- Is `idle` sitting at 0?
- Is `pending` growing?
- Are acquire timeouts occurring?
- Are connection creations failing?

### Step 5: Inspect the database

- Is query latency rising?
- Are CPU or I/O high?
- Are lock waits or deadlocks occurring?
- Are session counts excessive?
- Did query plans regress?

### Step 6: Inspect downstream services and network

- Are HTTP calls running inside transactions?
- Is downstream latency rising?
- Are network RTT or retransmissions abnormal?
- Are retries amplifying load?

### Step 7: Change one variable and retest

For example, if you suspect a slow query:
- Run `EXPLAIN`.
- Add or adjust an index in a test branch.
- Rerun the exact same workload.
- Compare latency and database resource usage.

Never raise pool size, CPU, heap, replicas, and change queries all at once. If numbers improve, you will not know which change fixed the bottleneck.

## 15. Evaluating R2DBC by workload

R2DBC is usually a stronger fit when:
- The app already uses WebFlux and needs end-to-end reactivity.
- High concurrency consists mainly of I/O-bound waiting.
- Thread-per-request or blocking pools are a measured bottleneck.
- The target database's R2DBC driver is mature and supports needed features.
- The team understands Reactor, cancellation, transaction contexts, and reactive debugging.
- Operations can monitor and tune reactive connection pools.

JDBC may be a better fit when:
- Current workloads meet SLOs at lower cost.
- Bottlenecks live in queries or the database rather than thread blocking.
- The app relies heavily on JPA persistence contexts, lazy loading, or JPA ecosystems.
- The R2DBC driver lacks required features or behavior.
- The team is not yet ready to operate reactive stacks.
- Migration cost and risk outweigh measured benefits.
- The workload is mostly batch/CPU-bound with no need for end-to-end reactivity.

Never decide based on a single-query microbenchmark. Weigh total cost:
- Performance on real workloads.
- Resource usage at target SLOs.
- Migration effort.
- Debuggability.
- Driver maturity.
- Observability.
- Code complexity.
- On-call readiness and team skills.

### 15.1. R2DBC does not reduce database connection count on its own

A reactive app handles high concurrency with fewer threads, yet each active database operation still requires a connection for its duration. Pushing concurrency too high with R2DBC still spikes pool pending acquires and overloads the database.

Bound concurrency and pools to database capacity. Never jump from 200 JDBC threads to 2,000 concurrent R2DBC queries without measuring.

### 15.2. R2DBC does not optimize SQL

If a query takes 800 ms due to a full table scan, R2DBC will not make it 20 ms just by being non-blocking. Database execution time still dominates request latency.

Optimize queries, indexes, projections, and transactions before or alongside driver decisions. Isolate the impact of each change so you know where improvements originate.

### 15.3. Reactive stacks require consistency

Calling blocking JDBC directly on WebFlux event-loop threads destroys reactive benefits. If temporary JDBC integration is necessary, offload blocking calls to a properly bounded scheduler/executor and document the blocking boundary in the architecture.

Not every component in a system has to be reactive at any cost. Choose boundaries based on workload characteristics and operational payoff.

## 16. Example benchmark comparison table

Suppose the same mixed read/write workload runs on equivalent test environments:

| Metric | JDBC | R2DBC |
|---|---:|---:|
| Throughput within SLO | 420 RPS | 610 RPS |
| p50 | 42 ms | 39 ms |
| p95 | 180 ms | 145 ms |
| p99 | 520 ms | 410 ms |
| App CPU | 72% | 64% |
| Peak heap | 1.8 GB | 1.5 GB |
| Peak threads | 420 | 110 |
| DB CPU | 68% | 70% |
| Acquire/pool wait p95 | 12 ms | 18 ms |
| Error rate | 0.08% | 0.06% |

These figures are purely illustrative, not real measurements or predictions for any specific application.

How to interpret:
- R2DBC achieved higher throughput within SLOs on this workload.
- p95/p99 improved, though pool wait ticked up slightly.
- Peak thread count dropped substantially.
- Database CPU stayed nearly flat, showing the database performed equivalent work.
- Soak tests, cancellation behavior, driver error handling, and operational overhead still need evaluation before deciding.

Never just say "R2DBC is 45% faster". Always state the workload, environment, load tier, SLOs, and run-to-run variance.

## 17. Benchmark report template

A report can follow this structure:

~~~text
Workload name:
Application version:
JDK:
Spring Boot:
Spring Data:
R2DBC driver:
Database version:
Dataset size:
Application replicas:
CPU/memory limits:
JDBC pool configuration:
R2DBC pool configuration:
Load generator:
Test duration:
Warm-up duration:
Arrival model:
Target RPS/concurrency:

Results:
- Throughput:
- p50/p95/p99:
- Errors/timeouts:
- CPU:
- Heap/GC:
- Thread count:
- Pool acquired/idle/pending:
- Acquire latency:
- DB CPU/I/O:
- Query latency:
- Active sessions:
- Rows/request:
- Response bytes:

Observed bottlenecks:
Changes tested:
Impact of changes:
Remaining limits:
Conclusion and decision:
~~~

Reports must record configuration and test conditions. A latency number without its accompanying workload, dataset, and environment cannot be reproduced.

## 18. Common load testing mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Testing a single trivial endpoint | Fails to reflect production traffic | Use a realistic workload mix |
| Dataset too small | Results reflect cache hits only | Use production-scale data and distribution |
| Skipping JVM warm-up | Pollutes metrics with startup/JIT overhead | Separate warm-up from measurement |
| Running load generator on app host | Generator contends for CPU and network | Run the generator on a separate machine |
| Looking only at average latency | Hides severe tail latency | Track p95 and p99 |
| Treating closed model as fixed RPS | Slow server throttles generator rate | Use an open model for fixed arrival rates |
| Ignoring dropped iterations | Assumes server handled target RPS | Monitor generator throughput and drops |
| Comparing different SQL queries | Conflates driver impact with SQL tuning | Keep query semantics identical |
| Running JDBC on the event loop | Invalidates benchmark and stalls requests | Isolate blocking JDBC properly |
| Measuring only thread count | Misses database or pool bottlenecks | Instrument the full stack |
| Enlarging pools to fix every slowdown | Overloads the database | Find why connections are held or queries are slow |
| Ignoring transaction duration | Misses connections held across downstream calls | Instrument transactions and trace spans |
| Skipping soak tests | Misses leaks and long-term degradation | Run extended steady-load tests |
| Keeping heavy profilers on during all runs | Skews benchmark measurements | Separate performance runs from profiling runs |
| Cherry-picking the best run | Biases conclusions | Repeat runs and report variance |
| Assuming R2DBC is always faster | Ignores workload fit and migration costs | Evaluate against SLOs and total cost |

## 19. End-to-end practical workflow

1. Define SLOs and capacity targets for each use case.
2. Gather endpoint ratios, queries, page sizes, and read/write mixes from real workloads.
3. Generate datasets with realistic scale and distributions.
4. Standardize application, database, JVM, and network environments.
5. Choose the right open or closed load model.
6. Run a smoke test to validate scripts and test data.
7. Warm up the application and database consistently.
8. Run load tests at target traffic and record p50/p95/p99, throughput, and errors.
9. Run stress, spike, and soak tests to find saturation points and long-term issues.
10. Collect HTTP, JVM, pool, database, and downstream telemetry.
11. Use traces, JFR, and execution plans to locate bottlenecks.
12. Change one variable at a time and rerun the same workload.
13. Benchmark JDBC and R2DBC with equivalent query semantics and SLOs.
14. Compare resource efficiency, not just raw latency.
15. Document limits, variance, and operational costs.
16. Adopt R2DBC only when measured gains fit the workload and outweigh migration costs.

## 20. Self-check exercises

### Exercise 1: Throughput and latency

R2DBC achieves 700 RPS with 2-second p99, while JDBC achieves 500 RPS with 300 ms p99. Can you conclude R2DBC is better?

Hint: Not if the p99 SLO is 500 ms. Higher throughput does not offset violating the latency SLO.

### Exercise 2: Average and percentiles

Average latency is 80 ms, yet p99 is 3 seconds. What should you inspect?

Hint: Trace the slow requests, query/lock waits, GC pauses, pool waits, downstream calls, and queueing. Averages hide tail latency.

### Exercise 3: Load generator

k6 is configured for 1,000 RPS, yet `dropped_iterations` is climbing. Can you conclude the server handled 1,000 RPS?

Hint: No. The generator could not launch all scheduled iterations; check actual achieved request rate and generator capacity.

### Exercise 4: Database bottleneck

JDBC and R2DBC show nearly identical query latencies, and database CPU sits at 95%. What should you investigate first?

Hint: Query plans, indexes, rows scanned, locks, and database capacity. Switching drivers will not resolve an SQL/database bottleneck.

### Exercise 5: Pool saturation

R2DBC `acquired` hits max, `idle` is 0, and `pending` is rising, while database CPU is low. What causes should you check?

Hint: Long transactions, downstream calls inside transactions, slow streams, connection leaks, pool configuration, or slow connection creation/validation.

### Exercise 6: Event loop

CPU is low, yet many WebFlux requests slow down together and thread dumps show event-loop threads waiting on JDBC. What is the conclusion?

Hint: Blocking calls on the event loop are stalling unrelated requests. Isolate blocking work or move that access path to non-blocking I/O.

### Exercise 7: Workload model

You want to sustain exactly 500 requests/second regardless of response slowdowns. Should you use an open or closed model?

Hint: An open model with a constant arrival rate, while monitoring generator `dropped_iterations` and queues.

### Exercise 8: Fair comparison

R2DBC uses a query with a new index while JDBC uses the old query, and the benchmark shows R2DBC is faster. Is that enough to credit R2DBC?

Hint: No. Run a comparison with equivalent queries to separate driver effects from SQL optimization.

### Exercise 9: Little's Law

At 100 RPS throughput and 200 ms average latency, roughly how many requests are in the system on average?

Hint: \(L = 100 \times 0.2 = 20\) requests. This is average HTTP concurrency, not database connection count.

### Exercise 10: Technology decision

An app serves 50 RPS, JDBC meets all SLOs, the database is the bottleneck, and the team lacks Reactor experience. Should you migrate to R2DBC solely to speed up the database?

Hint: There is no reason to expect R2DBC to speed up queries. Optimize the database first and weigh reactive benefits against migration and operational costs.

## 21. Key takeaways

- Load testing must start from SLOs and representative workloads, not an arbitrary RPS target.
- Track throughput, p50/p95/p99, error rate, concurrency, and saturation together.
- Average latency is insufficient for understanding tail latency.
- Open workload models hold arrival rate constant; closed models hold virtual user count constant and throttle when responses slow down.
- Check `dropped_iterations` to verify the load generator actually delivered the intended load.
- Keep datasets, caches, indexes, JVM, network, and database settings controlled when comparing.
- Separate warm-up from measurement windows and repeat runs.
- Collect telemetry across HTTP, JVM, R2DBC pool, database, network, and downstream services.
- `acquired` counts leased connections, not active executing queries.
- Correlate pool `pending` with transaction durations and query latencies to find root causes.
- Use traces, JFR/profiling, and `EXPLAIN` to isolate bottlenecks instead of tweaking many settings at once.
- R2DBC can cut thread pressure under high I/O-bound concurrency; it does not optimize SQL or expand database capacity.
- Blocking JDBC must never run on WebFlux event loops; isolate blocking calls properly in benchmarks.
- Compare JDBC and R2DBC with identical query semantics, datasets, workloads, SLOs, and environments.
- Measure resource efficiency, error rates, tail latency, and operational cost—not throughput alone.
- Run load, stress, spike, and soak tests because each exposes a different failure mode.
- Adopt R2DBC when measured benefits fit the workload and outweigh migration, debugging, and operational costs.

Evaluating R2DBC requires evidence from realistic workloads. Define clear SLOs, generate controlled load, measure end-to-end from HTTP to JVM, pools, and the database, and address bottlenecks layer by layer. By comparing JDBC and R2DBC over identical data and contracts, you can determine which model handles load better, uses resources more efficiently, and aligns with your team's operational capabilities.

# Load Testing for Cold Starts, Concurrency, and Downstream Limits

Serverless applications can scale rapidly when traffic rises, yet fast scaling does not mean every downstream component can absorb the matching load. A Java function can start slowly when spinning up new execution environments, surge concurrent invocations within seconds, and open bursts of connections to databases or external APIs. Measuring only average throughput can hide cold starts, tail latency, throttling, and downstream overload.

Serverless load testing must answer three questions:

1. **Cold start:** how long does the first request on a new execution environment take, and what share of requests are affected?
2. **Concurrency:** how far does the function scale before latency, error rates, or throttling violate SLOs?
3. **Downstream limits:** how many requests/connections can databases, connection pools, partner APIs, queues, or KMS sustain before becoming the bottleneck?

This lesson covers designing workloads, separating cold and warm starts, estimating concurrency, simulating HTTP and queue load, bounding dependency pressure, collecting metrics, and interpreting results. Examples use Java serverless and k6; the principles apply to AWS Lambda, Azure Functions, Google Cloud Functions/Cloud Run, and similar FaaS platforms.

## 1. How does serverless load testing differ from always-on application testing?

With fixed servers, teams typically measure how many requests per second a cluster of instances handles. Serverless introduces additional variables:

- The platform creates or reuses execution environments based on traffic and configuration.
- Requests may wait on runtime initialization, class loading, framework startup, and dependency connections.
- Increasing concurrency can spawn many independent JVMs/processes/containers and independent connection pools.
- Platforms enforce limits on concurrency, scaling rates, quotas, and execution duration.
- Different triggers carry different semantics: HTTP returns responses directly, queues accumulate backlogs and retries, and streams use partitions/shards and checkpoints.
- Costs can scale with invocation counts, execution duration, memory/CPU, requests to dependent services, and network egress.

Therefore, measure both the function and the full request path. A handler may run quickly inside the JVM while total duration remains high due to cold starts, DNS/TLS, connection pool waits, or slow partner APIs.

### Four result groups to separate

| Group | Question to answer | Example metrics |
|---|---|---|
| Latency | How long does a request take from client to final outcome? | End-to-end p50, p95, p99 and function duration |
| Capacity | How much load can the system handle steadily? | RPS, throughput, concurrency, queue drain rate |
| Reliability | How many errors does load trigger? | 5xx, timeouts, throttling, retries, dropped iterations |
| Resource/cost | How are resources and dependencies consumed? | CPU, memory, DB connections, API quotas, invocation cost |

Never declare a system healthy solely from high throughput. If p99 breaches the SLO or downstream dependencies are throttled, the system has not met operational targets.

## 2. Setting goals before generating load

Load testing is effective when starting from a concrete hypothesis and pass/fail criteria. For example:

> As load ramps from 50 to 300 requests/second, the Java HTTP function must keep p95 under 500 ms, error rate under 1%, database connections within the 80-connection cap, and queue age from growing unboundedly.

These numbers are illustrative. Real SLOs must come from product requirements, service quotas, and dependency budgets.

Before running, define:

1. **Workload:** which endpoints or events are invoked, read/write ratios, payload sizes, and downstream fan-out.
2. **Traffic profile:** steady baseline, peak hours, bursts, scheduled spikes, and projected growth.
3. **SLOs:** acceptable p95/p99 latency, error rate, queue processing time, and cold-start delay.
4. **Dependency budget:** limits on requests/sec, concurrent connections, transactions, quotas, and database/API timeouts.
5. **Scale limits:** max concurrency/instances, reserved concurrency, queue dispatch rates, or hosting plan scale-out limits.
6. **Test boundary:** environment, account/project, test data, run duration, max cost, and on-call observer.

### Workload matrix

| Profile | Description | Purpose |
|---|---|---|
| Baseline | Low, steady traffic | Measure latency and resource usage under normal conditions |
| Ramp/load | Gradual increase to target load | Identify capacity and degradation thresholds |
| Spike | Sudden traffic surge | Observe scale speed, cold starts, and downstream protection |
| Stress | Push beyond projected load | Find breaking points and failure modes |
| Soak | Hold steady load for extended duration | Detect leaks, pool exhaustion, backlog, and drift over time |
| Recovery | Drop load after stress/spike | Measure recovery time and backlog drain |
| Dependency limit | Simulated or real DB/API limits in sandbox | Verify backpressure, timeouts, retries, and circuit breakers |

Never start with maximum stress testing. Run a baseline, confirm generated load behaves as expected, and then ramp gradually so root causes stay clear.

## 3. Understanding cold starts and warm starts

A cold start happens when the platform creates a new execution environment or re-initializes the runtime before handling an invocation. In Java, tasks contributing to startup time include:

- Creating the process/container and starting the JVM.
- Loading classes, resolving dependencies, and running static initializers.
- Initializing dependency injection containers such as Spring.
- Creating SDK clients, HTTP connection pools, database pools, or TLS contexts.
- Loading configuration/secrets and running health/init logic.
- In certain configurations, restoring snapshots or running extra runtime initialization.

Warm invocations reuse an already-initialized execution environment and avoid most startup overhead. However, warm does not guarantee uniform latency: GC pauses, JIT compilation, pool contention, networking, and downstream load can still slow requests.

### Cold start is not a single fixed number

Cold starts depend on runtime, memory/CPU, framework, artifact size, deployment region, dependencies, and scaling configuration. A Java app using a heavy framework can have a markedly different startup profile from a slim Java handler without a DI container.

Do not compare averages alone. Report cold-start distributions separately: p50, p95, p99, min/max, and sample count. Cold starts may represent a small fraction of total requests while still pushing p99 past the SLO.

### Measuring cold starts on AWS Lambda

In Lambda, CloudWatch Logs `REPORT` lines can show `Init Duration` for invocations where an initialization phase occurred. With SnapStart, logs can report corresponding restore metrics such as `Restore Duration`. Parse logs carefully by runtime version and invocation type; do not assume every request lacking an `Init Duration` field represents identical cold-start conditions.

Useful metrics include:

- `Duration`: handler execution time, excluding the full latency observed by clients.
- `ConcurrentExecutions`: number of concurrent invocations.
- `Throttles`: throttled invocations.
- `Errors`: failed invocations.
- `Invocations`: invocation count.
- `ProvisionedConcurrencySpilloverInvocations`: requests exceeding provisioned concurrency and spilling onto standard concurrency.

To measure end-to-end latency, the load generator client must record time from sending the request to receiving the response. Combine client timing with initialization logs and traces to separate startup, handler, and dependency latency.

### Measuring cold starts on other platforms

On Cloud Run, cold starts occur when creating new instances or scaling from zero; correlate request latency and startup/instance telemetry with instance counts and min-instances settings. On Azure Functions, behavior depends on hosting plan, worker model, and scale controller; combine host/Application Insights telemetry with client request timing. Metric names and granularity differ by plan/runtime, so verify against official platform documentation and dashboards.

Never rely on a single cloud metric to represent all cold starts. Record request timestamps, instance/environment IDs if exposed by telemetry, init duration, and handler execution time.

## 4. Designing proper cold-start measurements

Cold starts are harder to measure than warm starts because platforms reuse environments. Sending consecutive requests to the same endpoint mostly yields warm invocations rather than a fresh cold start per request.

### Separating two experiments

**Warm experiment:**

1. Send a warmup wave to create and initialize environments.
2. Wait until traffic stabilizes.
3. Sustain load for the defined measurement window.
4. Measure p50/p95/p99, throughput, handler duration, and dependency latency.

**Cold/scale-out experiment:**

1. Use a dedicated test environment matching production configuration.
2. Set min instances/provisioned concurrency to 0 when measuring scale-from-zero and permitted by the platform.
3. Space out traffic bursts enough for environments to be reclaimed per platform policy, or deploy isolated targets per batch when strict isolation is required.
4. Trigger a sharp traffic surge to observe new environment creation and startup distribution.
5. Attach correlation IDs and correlate client timing with startup logs/traces.

An idle interval does not guarantee immediate environment reclamation by the platform. You cannot force a specific request to be a guaranteed cold start solely by waiting a fixed interval. When per-initialization measurements are needed, use isolated deployments/targets or telemetry identifying new environments, and document the method's limits.

### Avoiding skewed results

- Do not enable provisioned concurrency/min instances during scale-from-zero tests when measuring organic cold starts.
- Run a separate experiment to evaluate provisioned concurrency or min instances.
- Never mix cold and warm requests into a single combined average.
- Never draw p99 conclusions from a tiny run; gather sufficient cold-start samples.
- Keep artifacts, memory/CPU, region, networking, and dependencies identical across comparisons.
- Record JIT, cache, and connection-pool states since they alter warm latency over time.
- Verify the load generator itself is not the bottleneck.

### Comparing cold-start mitigation strategies

| Strategy | Expected effect | What to measure |
|---|---|---|
| Increase memory/CPU | Can shorten init and handler startup | Init duration, cost/invocation, and CPU profile |
| Trim dependencies/classpath | Reduces class loading and initialization | Startup distribution, artifact size |
| Lazy initialization | Moves part of init off the first-request path or initializes on demand | First-use latency and warm latency |
| Native image/AOT if runtime supports it | Can reduce startup, trading off build/memory | Startup, throughput, compatibility, and memory |
| AWS Lambda SnapStart | Restores environment from snapshot on supported runtimes | Restore duration, hook behavior, and request latency |
| Provisioned concurrency/min instances | Keeps pre-initialized capacity warm | Cold-start rate, spillover, idle cost, and burst scaling |

Do not optimize cold starts blindly by throwing resources at them. If p99 is dominated by the database or a partner API, faster startup may not improve end-to-end latency.

## 5. Estimating concurrency before running tests

A straightforward estimate comes from Little's Law:

\[
L = \lambda \times W
\]

Where:

- `L` is the average number of requests in the system (concurrency/in-flight work).
- `λ` is throughput, e.g., requests per second.
- `W` is average processing time in seconds.

For example, if an endpoint receives 200 requests/second and average processing time is 0.4 seconds:

\[
L = 200 \times 0.4 = 80
\]

The system needs roughly 80 concurrent in-flight requests at steady state. When latency rises, concurrency rises as well for a constant arrival rate. Thus, a slow downstream service keeps more invocations alive simultaneously, driving up connection-pool pressure.

This is a steady-state mean estimate. Capacity planning requires extra headroom for bursts, latency distributions, fan-out, retries, and platform limits.

### Calculating downstream fan-out

One invocation may trigger multiple downstream calls. If each invocation calls 3 APIs and 1 database query, dependency concurrency does not equal function concurrency.

Example:

- 80 concurrent invocations.
- Each invocation issues up to 2 parallel requests to API A.
- Each invocation holds 1 DB connection during processing.

Then API A can see up to roughly 160 concurrent requests, while the database can see up to roughly 80 held connections from this worker alone—before counting connections from other services.

Build a fan-out table per dependency, factoring in retries and background work spawned from handlers.

## 6. Calculating connection budgets for databases and APIs

Each execution environment/container can own its own connection pool. Total potential connections equal the sum of pools across all active instances.

Conservative upper bound:

\[
Connections_{max} \approx Instances_{max} \times PoolSize_{per\ instance}
\]

For example, Cloud Run is capped at 20 instances and each instance runs a HikariCP pool of max 8 connections:

\[
20 \times 8 = 160\ connections
\]

If the database allocates only 100 connections to the application, this configuration can breach the budget even when every instance behaves normally. Also account for admin connections, migrations, dashboards, other services, and safety headroom.

With Lambda, max concurrency roughly equals concurrent execution environments for a standard function. If each environment opens a pool holding up to 5 connections, the theoretical upper bound is concurrency times 5. Pools may open connections lazily, yet you should never rely on lazy opening to ignore hard limits.

### Java HikariCP: configuring a bounded pool

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class DataSources {
    private static final HikariDataSource DATA_SOURCE = create();

    private DataSources() {}

    private static HikariDataSource create() {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(System.getenv("JDBC_URL"));
        config.setUsername(System.getenv("DB_USERNAME"));
        config.setPassword(System.getenv("DB_PASSWORD"));
        config.setMaximumPoolSize(2);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(1500);
        config.setValidationTimeout(500);
        config.setPoolName("orders-worker-pool");
        return new HikariDataSource(config);
    }

    public static HikariDataSource get() {
        return DATA_SOURCE;
    }
}
```

This example only illustrates a small pool for a single execution environment. `maximumPoolSize=2` is not universal for every app. Choose it from total system concurrency, max instances, and the database connection budget. Never create a new `HikariDataSource` per invocation; reuse the pool within the execution environment and return connections promptly after each operation.

For Lambda connecting to Amazon RDS, consider RDS Proxy where appropriate. A proxy reduces direct database connections and manages pooling, though transactions, session state, or certain statements can pin connections. Always load test client connection counts, backend connections, and pinning rates.

### Connection pools do not replace concurrency caps

If each instance has a 2-connection pool yet the platform scales to 500 instances, the database can still receive hundreds of connections. Combine controls:

- Cap total function/service concurrency.
- Cap max instances or concurrency per instance.
- Keep pools small with bounded acquisition timeouts.
- Use proxies/poolers where appropriate.
- Cache safe read data where possible.
- Eliminate long transactions and unnecessary fan-out.

## 7. Downstream limits and backpressure

Serverless can scale faster than dependencies can serve. For example, a partner API permits only 100 requests/second while a function bursts to 500 requests/second. Without limits, the system triggers 429/5xx responses, retries, and amplifies load.

Backpressure slows down or rejects incoming work when downstream approaches capacity. Common mechanisms:

1. **Concurrency cap:** limit concurrent invocations or instances.
2. **Rate limit:** cap requests per second to a dependency.
3. **Bounded connection pool:** cap connections and wait timeouts.
4. **Queue:** decouple producers from consumers and dispatch at a sustainable downstream rate.
5. **Bulkhead:** isolate resources per dependency so one slow service does not starve all workers.
6. **Circuit breaker:** temporarily halt calls to a persistently failing dependency, then probe under control.
7. **Timeouts and retry budgets:** bound duration and attempts using backoff/jitter.

### Never retry every error

Classify errors before retrying:

| Error | Recommended behavior |
|---|---|
| Network timeout or transient error | Bounded retries with exponential backoff and jitter |
| HTTP 429 | Honor `Retry-After` if present, reduce rate, and cap concurrency |
| HTTP 5xx | Bounded retries if the operation is idempotent |
| HTTP 400/validation | Do not retry; fix payload or mark business error |
| HTTP 401/403 | Do not retry continuously; check credentials/permissions |
| Database connection pool exhausted | Lower concurrency, use bounded wait timeout, and inspect pool budget |
| Quota exceeded | Throttle load or request controlled quota increase |

If the SDK retries 3 times, the app retries 3 times, and the queue redelivers 5 times, one message can trigger far more downstream calls than intended. Define which layer owns retries, the total retry budget, and idempotency keys.

### Example fan-out cap in Java

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class PartnerApiGate {
    // Cap concurrency within one execution environment.
    private static final Semaphore PER_INSTANCE = new Semaphore(4);

    public <T> T call(CheckedSupplier<T> operation) throws Exception {
        boolean acquired = PER_INSTANCE.tryAcquire(100, TimeUnit.MILLISECONDS);
        if (!acquired) {
            throw new DownstreamBusyException("Partner API concurrency budget reached");
        }

        try {
            return operation.get();
        } finally {
            PER_INSTANCE.release();
        }
    }

    @FunctionalInterface
    public interface CheckedSupplier<T> {
        T get() throws Exception;
    }

    public static final class DownstreamBusyException extends RuntimeException {
        public DownstreamBusyException(String message) {
            super(message);
        }
    }
}
```

This semaphore only bounds concurrency inside a single JVM/instance. If the platform spins up 50 instances, total requests can still reach 200. To enforce global limits, pair it with platform concurrency caps, queue dispatch rates, or a properly designed distributed rate limiter. Configure HTTP client timeouts separately; a semaphore will not cancel a hung network call.

## 8. Choosing open workloads vs. closed workloads

Load generators generate traffic using two models:

- **Closed model:** fixed number of virtual users; each user sends a request and waits for the response before sending the next.
- **Open model:** fixed arrival rate; new requests launch at a configured rate regardless of whether earlier requests finished.

Closed models work well when simulating a bounded pool of concurrent users. However, when a service slows down, each VU sends fewer requests, artificially lowering offered load. This can mask overload. Open models test whether the system sustains a fixed arrival rate; if the service slows down, queued requests pile up and expose bottlenecks.

For APIs with event-driven traffic or request bursts, run at least one open-model test. Check `dropped_iterations` or equivalent load-generator metrics to ensure the tool actually generated the intended load.

## 9. HTTP load test example with k6

k6 supports arrival-rate executors, ramping, thresholds, and custom tags. The example below ramps request rates against a job-creation endpoint. Latency thresholds are placeholders; replace them with your system's SLOs.

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    orders_api: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 30,
      maxVUs: 300,
      stages: [
        { target: 25, duration: '2m' },
        { target: 50, duration: '3m' },
        { target: 100, duration: '3m' },
        { target: 150, duration: '3m' },
        { target: 0, duration: '1m' }
      ]
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    dropped_iterations: ['count<1']
  }
};

export default function () {
  const runId = __ENV.TEST_RUN_ID;
  const baseUrl = __ENV.BASE_URL;
  const payload = JSON.stringify({
    testRunId: runId,
    requestId: `${__VU}-${__ITER}`,
    orderType: 'load-test'
  });

  const response = http.post(`${baseUrl}/api/orders`, payload, {
    headers: {
      'Content-Type': 'application/json',
      'X-Load-Test': runId
    },
    tags: { test_run: runId }
  });

  check(response, {
    'accepted or created': (res) => res.status === 202 || res.status === 201
  });
}
```

Run in a test environment using dedicated environment variables:

```bash
k6 run -e BASE_URL=https://test-api.example.internal \
  -e TEST_RUN_ID=serverless-capacity-001 orders-load.js
```

The script drives load by arrival rate. `preAllocatedVUs` and `maxVUs` must be high enough to sustain the target rate; if VUs run out, k6 records dropped iterations. Check load-generator CPU/memory and k6 metrics before concluding the serverless service hit its limit.

### Dedicated cold-start test

You cannot guarantee every iteration of the script above hits a cold start. Use this script to send traffic bursts after an environment scales to zero or after deploying a fresh test target, correlating each request with platform logs to classify cold vs. warm.

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 1,
  iterations: 20,
  thresholds: {
    http_req_failed: ['rate<0.01']
  }
};

export default function () {
  const response = http.get(`${__ENV.BASE_URL}/health/ready`, {
    headers: { 'X-Load-Test': __ENV.TEST_RUN_ID }
  });
  check(response, { 'health is ready': (res) => res.status === 200 });
  sleep(2);
}
```

This script measures latency across spaced requests without proving by itself which request was cold. Pair it with instance/init telemetry and controlled scale-from-zero experiments. To measure burst cold scale-out, ramp VUs/rate and count newly created instances; to measure warm performance, sustain load after the system stabilizes.

## 10. Load testing queue-triggered functions

For queue triggers, measuring producer send latency is not enough. Measure the time from enqueue to worker completion, consumer throughput, backlog, and oldest message age.

Key metrics:

- Messages sent/received/deleted.
- Queue depth or visible/not-visible message counts.
- Age of oldest message.
- Lambda/Function invocations, concurrency, duration, errors, and throttles.
- Records succeeded, retried, duplicated, and sent to DLQ.
- End-to-end time from enqueue to business completion.
- Downstream database/API connections and throughput.

### Designing a queue test

1. Generate messages with `testRunId`, unique `eventId`, and payloads sized close to production.
2. Ramp the producer rate in steps, e.g., 10, 25, 50, 100 messages/second.
3. Configure queue/trigger batch size and concurrency caps matching the workload.
4. Have the worker process idempotently and record a measurable completion timestamp.
5. Monitor queue age, backlog, worker concurrency, and downstream health.
6. Stop the producer and measure how long the queue takes to drain back to normal.
7. Check the DLQ and confirm zero lost messages or unexpected duplicate processing.

With SQS and Lambda, event source mapping `MaximumConcurrency` or reserved concurrency can throttle the consumer. With Azure Queue/Service Bus triggers or Google Cloud Tasks/Pub/Sub, use each service's concurrency/dispatch controls. Never assume identical batch sizes, ordering, or retries across platforms.

### Throughput of a batch consumer

A rough approximation for a queue worker:

\[
Throughput \approx \frac{ConcurrentInvocations \times BatchSize}{AverageBatchDuration}
\]

For example, 10 concurrent invocations, batch size 5, and 2-second batch processing time yield a theoretical throughput of about 25 messages/second. Real throughput also depends on per-record processing time, partial batch failures, poller limits, downstream latency, and visibility timeouts.

If each message issues multiple queries or API calls, calculate dependency load by record count and fan-out rather than invocation count alone.

## 11. Metrics and tracing to collect

Load tests require unified observability from client to dependencies.

| Layer | Metrics/logs/traces |
|---|---|
| Load generator | Offered RPS, completed RPS, VUs, dropped iterations, p50/p95/p99, network errors |
| API/gateway | Request count, 4xx/5xx, 429, latency, throttling, auth failures |
| Function platform | Invocations, concurrency, duration, errors, throttles, init/restore, memory, CPU/instance count |
| Java runtime | Startup phase, GC pauses, heap, thread count, connection pool active/idle/pending |
| Queue | Visible/not-visible messages, age of oldest, receive/delete, retries, DLQ |
| Database | Active connections, pool wait, CPU, IOPS, lock wait, query latency, transaction errors |
| External API | RPS, 429/5xx, latency, timeouts, quota usage |
| KMS/secrets service | Request count, throttling, AccessDenied, latency, and retries |

### Distinguishing platform duration from end-to-end latency

Function duration usually measures only execution inside the platform. Clients also experience DNS, TLS handshakes, gateway overhead, networking, cold starts, or queue wait time before workers begin. With queues, producer requests can return success immediately while work waits in the backlog.

Propagate correlation IDs or trace IDs end to end. For HTTP, record timestamps at the client, gateway, handler, and dependencies. For queues, attach event IDs and enqueue timestamps, then record completion timestamps. Never log sensitive payloads for load testing.

### Measuring tail latency

Report p50, p90, p95, p99, and p99.9 when sample counts permit. Averages hide small cohorts of requests suffering cold starts or long pool waits. When comparing two configurations, keep workloads and sample sizes comparable and report variance across runs.

## 12. Designing concurrency limit tests

The goal is finding the point where adding concurrency stops improving throughput or begins degrading SLOs.

A procedure:

1. Start at low concurrency and capture a baseline.
2. Ramp arrival rates in steps, holding each step long enough for autoscaling to stabilize.
3. Record actual concurrency, instance counts, throughput, and p95/p99.
4. Identify the first point showing throttling, rising queue age, rising error rates, or rising downstream pool wait.
5. Reduce load to verify system recovery.
6. Repeat with different max concurrency/instance limits to evaluate trade-offs.

Platform limits to document:

- AWS Lambda: account/function concurrency, reserved concurrency, provisioned concurrency, event source mapping maximum concurrency, and relevant quotas.
- Cloud Run: maximum instances, concurrency per instance, minimum instances, and CPU/memory allocation.
- Azure Functions: hosting plan, scale-out limit, per-instance concurrency, and trigger/worker limits.

Configuration names and semantics vary by plan/runtime/region. Inspect actual configuration and account quotas before testing; do not rely on undocumented defaults.

### Base concurrency caps on dependency budgets

If a database allocates only 60 connections to workers and each instance uses a pool of up to 3 connections, an initial instance cap can be derived from that budget after subtracting headroom and other services' connections. If a function calls an external API with a 100 RPS limit, factor in both concurrency and average call duration to pick the cap. You may need a rate limiter rather than a concurrency cap alone when API latency fluctuates.

Never set max concurrency to the account limit and hope downstream self-regulates. Platform concurrency is one of the strongest guardrails protecting dependencies.

## 13. Testing timeouts, retries, and overload behavior

A serverless system can fail under overload in several ways:

- Functions get throttled before executing.
- Requests wait at the gateway and time out.
- Connection pools fill up and handlers wait too long.
- Databases/APIs return 429 or 5xx.
- Functions time out after committing a side effect.
- Queue retries reprocess the same message.
- Retries across multiple layers amplify load.

Test these scenarios under control:

| Scenario | How to induce | Expected outcome |
|---|---|---|
| Function concurrency cap | Lower cap in test env and raise RPS | Predictable throttling; client retries per policy; downstream protected |
| DB pool exhaustion | Lower pool size or DB connection budget in sandbox | Bounded pool wait timeout; no infinite hangs; errors classified |
| API 429 | Mock server returns 429 above RPS threshold | Client slows down, honors Retry-After, avoids retry storm |
| API timeout | Mock server delays response past client timeout | Call aborts/times out, threads are not held indefinitely |
| Function timeout | Test handler runs longer than timeout | Observe retry/redelivery and verify idempotency |
| Queue backlog | Producer outpaces consumer for a bounded window | Queue age grows predictably and drains once producer stops |
| Recovery | Restore dependency after fault | Backlog drains and latency returns to baseline |

Never induce errors by breaking production dependencies. Use mocks/stubs, sandboxes, or dedicated test quotas to test overload.

## 14. Testing autoscaling and recovery

Autoscaling takes time to scale out, during which downstream systems may already absorb queued spikes before new instances are ready. Measure:

- Time from arrival-rate increase until instances/concurrency rise.
- Share of requests handled by newly spawned environments.
- Time from peak load until backlog clears.
- Instances remaining active after load drops.
- Open connections and how quickly pools shrink.
- Residual errors/throttling lingering after dependencies recover.

For queues, measure queue drain time after stopping the producer. For HTTP, measure how fast latency and error rates return to baseline. For scheduled workloads, verify subsequent runs do not overlap stale backlogs.

### Testing min instances/provisioned capacity separately

If the product requires low latency on the very first request, run a separate test with min instances/provisioned concurrency. Compare:

- Cold-start rate and p95/p99.
- Scale-out time when bursting past provisioned capacity.
- Spillover/concurrency beyond provisioned capacity.
- Idle cost during zero traffic.
- Handling bursts larger than warm capacity.

Provisioned capacity cuts a share of cold starts without removing downstream limits or startup latency on overflow instances.

## 15. Interpreting results and finding bottlenecks

Do not look at a single metric in isolation. Correlate signals to pinpoint the limiting component.

| Signal | Likely cause | Where to investigate |
|---|---|---|
| High client p99, low function duration | Gateway, network, cold start, or queue delay | Compare client timing, init logs, traces, and queue age |
| High init duration, good warm duration | JVM/framework/classpath/startup logic | Profile class loading, DI, static init, artifact size, and memory |
| Rising concurrency hits DB connection cap | Pool per instance too large or max instances too high | Recalculate connection budget, use proxy/pooler, lower concurrency |
| Flat throughput, rising p95, high DB CPU/locks | Database is the bottleneck | Query plans, indexes, transactions, connections, and write contention |
| Function throttles while downstream is idle | Function/account concurrency cap or quota | Inspect reserved/max concurrency and account quotas |
| Rising API 429s alongside retry counts | Partner rate limit and retry storm | Lower dispatch rate, honor Retry-After, bound retries |
| Growing queue age despite high concurrency | Slow worker, blocked downstream, or batch errors | Check duration, partial failures, DLQ, and dependency latency |
| Dropped iterations in k6 | Load generator lacks VUs/resources or cannot reach target rate | Scale generator capacity, distribute generators, check CPU/network |
| Latency creeping up in soak test | Leaks, pool/thread accumulation, GC, or cache growth | Heap/GC, connection leaks, thread counts, and memory trends |
| Slow recovery after spike | Backlog, retry schedule, or dependency cooldown | Queue drain, retry budget, circuit breaker, and scale-in behavior |

### Isolating bottlenecks by changing one variable at a time

When latency climbs, do not change memory, concurrency, pool size, and timeouts simultaneously. Change one variable at a time or run a small experiment matrix to isolate impact. Record configuration, artifact hashes, region, workload, and results for reproducibility.

## 16. SLOs and pass/fail thresholds

Define thresholds before running. Example for an HTTP endpoint:

| Metric | Example threshold |
|---|---:|
| p95 end-to-end latency | Under 500 ms |
| p99 end-to-end latency | Under 1,000 ms |
| HTTP 5xx + timeouts | Under 1% |
| Dropped iterations | 0 |
| DB connection usage | Under 80% of service budget |
| Downstream 429s | Not continuously rising at target load |
| Queue age | Within defined processing SLA |

Replace example thresholds with real SLOs. For synchronous APIs, end-to-end p95/p99 matters most. For queue workers, queue age and time-to-completion are often more meaningful than individual invocation latency.

A test passes only if offered load reached target levels, the generator did not bottleneck, error rates stayed within bounds, tail latency met SLOs, and downstream stayed within budget. If the load generator could not send enough traffic, results do not prove the service can handle that load.

## 17. Cost and safety during load testing

Load tests can incur major costs because serverless autoscales and downstream systems bill per request/connection/throughput. Before running:

- Use a dedicated account/project/subscription and isolated test data.
- Set budgets and concurrency/instance caps at approved levels.
- Rate-limit or mock partner APIs.
- Use synthetic data, avoiding personal or production data.
- Set TTL/cleanup for test objects, queues, database records, and logs.
- Define an immediate abort mechanism when cost or error thresholds trip.
- Notify operators if tests share dependencies in a staging environment.
- Never run spike/stress tests against production or third-party services without approval and coordination.

Track cost by run ID/tag if the platform supports it. Include function invocations, memory/duration, provisioned capacity, log ingestion, databases, NAT, KMS calls, and data transfer.

## 18. Complete load testing workflow

A repeatable workflow:

1. **Define SLOs and workload.** Pick RPS, payloads, operation ratios, bursts, and duration.
2. **Verify test boundaries.** Confirm environment, quotas, data, downstream mocks/sandboxes, budget, and on-call owner.
3. **Snapshot configuration.** Record runtime, artifact hash, memory/CPU, timeouts, concurrency, min instances, pool sizes, region, and queue policies.
4. **Run warm baseline.** Measure p50/p95/p99, duration, resources, and dependencies.
5. **Run cold/scale-from-zero.** Separate init/restore from warm requests, gather enough samples, and note measurement limits.
6. **Run ramp/load.** Step up offered rate to target load and slightly beyond under control.
7. **Run spike/stress.** Measure scale-out, throttling, and dependency protection.
8. **Run dependency-limit tests.** Lower quotas or simulate 429/timeout/pool exhaustion in sandbox.
9. **Run soak and recovery.** Hold load, stop load, and measure backlog drain and recovery time.
10. **Analyze bottlenecks.** Correlate client, platform, Java runtime, queue, and dependency metrics.
11. **Tune one variable.** Adjust memory, concurrency, pool, or rate limit and re-run the identical workload.
12. **Archive the report.** Save results, configuration, charts, limitations, and next actions.

## 19. Pre-capacity-signoff checklist

- [ ] Workload reflects realistic request rates, payload sizes, fan-out, and read/write ratios.
- [ ] Both open-model and closed-model tests are included where appropriate.
- [ ] Load generator is not a bottleneck; dropped iterations are checked.
- [ ] Cold starts and warm invocations are analyzed separately.
- [ ] Sample counts are sufficient to evaluate p95/p99 and startup distributions.
- [ ] Concurrency is estimated from arrival rate and latency with burst headroom.
- [ ] Connection budget accounts for max instances/concurrency times pool size.
- [ ] Fan-out, retries, and rate limits are verified per downstream dependency.
- [ ] Queue tests measure backlog, oldest-message age, and drain time.
- [ ] Timeouts, 429s, 5xx, throttling, and pool exhaustion are simulated safely.
- [ ] Recovery after spikes and dependency failures is tested.
- [ ] Provisioned capacity/min instances are tested separately if used.
- [ ] SLOs and pass/fail thresholds are defined upfront.
- [ ] Costs, quotas, test data, and emergency abort procedures are controlled.
- [ ] Results are saved with artifact/configuration/run IDs for reproducibility.

## Conclusion

Serverless load testing must measure cold starts, warm performance, concurrency, and downstream resilience together. Combine client timing with platform logs/traces to separate startup from handler execution; apply Little's Law and connection budgets to estimate concurrency; run open-arrival workloads to test offered rates; and watch queue age, pool waits, throttling, and dependency latency. A sound design meets SLOs under target load, bounds pressure on databases/APIs, and recovers from bursts without triggering retry storms. Record configurations and workloads so every Java function optimization can be verified through reproducible measurements.

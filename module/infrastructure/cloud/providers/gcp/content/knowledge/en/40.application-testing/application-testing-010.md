# Load Testing for Cloud Run, GKE, and Data Applications

A Java or Spring Boot API can respond quickly with only a few users, yet slow down markedly when hundreds of concurrent requests access Cloud SQL, Cloud Storage, or Pub/Sub. On Google Cloud, autoscaling on Cloud Run and Google Kubernetes Engine (GKE) helps absorb fluctuating load, but **autoscaling does not eliminate downstream dependency limits**. CPU, connection pools, database connection caps, API quotas, retries, and queues can all become bottlenecks.

**Load testing** is the process of generating traffic representative of expected usage, measuring system responses, and finding limits before deploying or scaling up. The goal is not merely to determine how many requests/second a system survives, but to verify latency, error rates, autoscaling behavior, recovery capability, cost, and data correctness.

This lesson explains how to design load scenarios, measure SLIs/SLOs, use tools such as k6, analyze Cloud Run and GKE behavior, test applications backed by Cloud SQL, Pub/Sub, and other data services, and feed results into the release process.

## 1. How Does Load Testing Differ from Other Tests?

Load testing is one subset of performance testing and is not synonymous with every kind of performance check.

| Test Type | Goal | Example |
|---|---|---|
| Unit/integration | Verify logic and component wiring | Repository commits transaction accurately to PostgreSQL |
| E2E functional | Verify a complete business journey | Create order, emit event, and confirm status |
| Load | Evaluate system under target traffic | 200 requests/second for 15 minutes |
| Stress | Push load past design thresholds to find breaking points | Ramp up until p95/5xx exceed thresholds |
| Spike | Evaluate response to short sharp surges | Traffic multiplies briefly over a short window |
| Soak/endurance | Detect degradation under sustained load | Run 2 hours at steady traffic to catch memory leaks |
| Capacity | Estimate resources and cost for a load level | Number of instances, Pods, CPUs, and DB connections required |
| Resilience/fault | Test behavior under controlled faults | A node loses connectivity while serving live traffic |

A load test can achieve its target throughput yet still fail if it writes duplicate orders or floods queues. Therefore, monitor both **performance** and **business outcome correctness**.

### Choosing the Right Load Unit

Depending on the application, load can be expressed as:

- Requests per second (RPS) or transactions per second (TPS).
- Concurrent virtual users (VUs).
- Messages per second through Pub/Sub.
- Database queries per second and connection counts.
- Objects/bytes read or written to Cloud Storage.
- Events or bytes processed through a data pipeline.

You cannot simply assume 100 virtual users equal 100 requests/second. A virtual user might send one request and wait several seconds, or issue bursts back-to-back. Behavior and pacing must be defined explicitly.

## 2. Building a Load Model from Real Behavior

A good load test models primary user journeys rather than hammering a single easily cached endpoint.

Example e-commerce application with three flows:

| Journey | Illustrative Traffic Share | Characteristics |
|---|---:|---|
| Read product catalog | 65% | Read-heavy, cacheable |
| View order details | 25% | DB read, requires authorization checks |
| Create order | 10% | DB write, emits event, requires idempotency |

If the target is 100 requests/second and those weights reflect live traffic, design a scenario emitting roughly 65 catalog reads, 25 order lookups, and 10 order creations per second. This is only illustrative: weights, think times, and payload sizes must come from operational telemetry or explicitly documented business assumptions.

Specify:

1. Read/write request ratios.
2. Request and response payload sizes.
3. Cache hit/miss ratios.
4. Auth success vs. rejection ratios.
5. Database dataset size and key distribution.
6. Delay between user actions (think time).
7. Traffic distribution across regions, peak hours, and clients.
8. Downstream dependency call frequency and induced retries.

In particular, data applications must be tested against a sufficiently large dataset. Queries against a 100-row table do not represent production tables with tens of millions of rows and markedly different index distributions.

### Open Model vs. Closed Model

There are two common ways to drive load:

- **Closed model:** maintains a fixed number of virtual users. Each user waits for a response before sending the next request. When the server slows down, the request generation rate drops.
- **Open model:** controls the rate of newly started requests/iterations—such as a target iterations per second—regardless of whether server responses slow down. Suits modeling external arrival traffic that does not back off just because processing slowed.

For APIs whose incoming traffic is measured in RPS, arrival-rate executors keep target load consistent. For interactive journeys with think time, a VU model may fit better.

Never compare two test runs produced under different load models without normalizing conditions.

## 3. Defining SLIs, SLOs, and Passing Criteria

Before writing scripts, define expected quality targets and stop conditions.

### Key Metrics

- **Throughput:** successful requests or transactions completed per second.
- **Latency:** request/operation completion time; track p50, p95, and p99.
- **Error rate:** application errors, HTTP 5xx, timeouts, or failed operations.
- **Saturation:** CPU, memory, connection pools, queues, quotas, and autoscaling limits.
- **Correctness:** orders created successfully, duplicate records, dropped messages, or data drift.
- **Recovery:** time to return to baseline after a spike or load termination.

Illustrative SLO example:

> At 150 requests/second for 15 minutes, at least 99.5% of valid requests succeed, p95 latency stays under 600 ms, and zero duplicate orders are created.

These thresholds are learning placeholders. Real SLOs must derive from product requirements, production telemetry, and error budgets.

### Never Use Averages to Hide Tail Latency

If 95% of requests finish under 300 ms while the remaining 5% take 5 seconds, the mean can look acceptable even as a slice of users suffers terrible performance. Track p95/p99 and break them down by endpoint, cache status, and request type.

Measure latency across multiple layers:

| Measurement Layer | Includes | Question |
|---|---|---|
| Client end-to-end | DNS, TLS, network, gateway, server, and response | How long does the user actually wait? |
| Load balancer / Cloud Run request | Request duration recorded by the platform | Is slowness in the outer network or inside the service? |
| Application timer | In-app logic and dependency calls | Which code path is slow? |
| Dependency timer | Cloud SQL, Pub/Sub, Storage, or external HTTP services | Where is the bottleneck? |
| Queue latency | Wait time before message processing | Are events processed within deadline? |

### Understanding Throughput and Concurrency

A useful steady-state approximation from Little's Law:

\[
L \approx \lambda W
\]

Where `L` is the average number of concurrent requests in flight, `\lambda` is completed requests per second, and `W` is average duration per request (seconds). For instance, at 200 requests/second and 0.25 seconds per request, average concurrent in-flight requests sit near 50.

This is a steady-state average relationship; it does not mean configuring a concurrency limit of 50 suffices. Bursts, p99 latency, retries, DB connections, and scale-up lag can demand significantly more capacity.

## 4. Guardrails: Scope, Approvals, and Budgets

Load tests can rack up substantial bills, exhaust quotas, or disrupt live services. Establish guardrails before generating traffic.

### Test Environment

Prefer a project/namespace/bucket/database created exclusively for testing. If a shared staging environment must be used:

- Obtain approval from application owners and operators.
- Document target project, region, endpoint, time window, and maximum load rate.
- Never access unauthorized customer data.
- Never run write/delete load scenarios against production without an approved plan.
- Cap VUs/RPS and duration, with an operator-controlled kill switch.
- Enforce budgets, quotas, cost alerts, and a cleanup plan.
- Use a dedicated least-privilege identity for the load generator.

Never base stop conditions solely on HTTP error codes. If DB CPU or connection count reaches dangerous levels, abort even if the API still returns HTTP 200.

### Safe Data and Endpoints

- Use synthetic or policy-compliant anonymized data.
- Tag every object, event, and record with `runId` for verification and cleanup.
- Attach idempotency keys to write operations.
- Avoid triggering real emails, payments, SMS, or partner webhooks during load runs.
- Never embed access tokens, session IDs, or personal data in metric labels/tags.
- Bound log/artifact retention per security policy.

### Sample Stop Conditions

| Signal | Illustrative Action Threshold |
|---|---|
| HTTP 5xx exceeds threshold | Stop or throttle back if sustained beyond a defined window |
| p99 latency spikes sharply | Inspect saturation instead of continuing blind stress |
| Cloud SQL nears connection limit | Lower RPS to prevent pool exhaustion and outage |
| Pub/Sub backlog grows continuously | Halt publishing so consumers can drain backlog |
| Load generator CPU maxed out | Discard run results as invalid server measurements |
| Cost or quota exceeds budget | Abort test and run cleanup |

Exact thresholds must be defined in the test plan rather than copied across systems.

## 5. Architecture of a Load Test Run

A test can run from an isolated runner (VM, Kubernetes Job, or dedicated load-generator platform), hitting the API while collecting metrics from both the client and Cloud Monitoring.

~~~mermaid
flowchart TD
    A[Test plan and SLO] --> B[Prepare isolated data and environment]
    B --> C[Load generator]
    C --> D[Cloud Run or GKE API]
    D --> E[Cloud SQL and storage]
    D --> F[Pub/Sub]
    F --> G[Async consumers]
    C --> H[Client metrics]
    D --> I[Cloud Monitoring and Logging]
    E --> I
    F --> I
    G --> I
    H --> J[Correlate results by run ID]
    I --> J
    J --> K[Pass fail report and remediation]
~~~

Before running, record baseline state:

- Commit, container image digest, service revision, or Deployment version.
- CPU/memory, concurrency, autoscaling bounds, min/max instances, or replicas.
- Database tier, connection limits, queries/indexes, and dataset size.
- Quotas, region, networking, load balancer, and caches.
- Generator configuration, runner region, VUs/RPS, and duration.

Do not change multiple variables between baseline measurements; changing CPU, replica count, cache, and pool size simultaneously obscures which change caused the effect.

## 6. Choosing Load Generation Tools

| Tool | Characteristics | Best Fit |
|---|---|---|
| k6 | JavaScript scripts, thresholds, multiple executors, easy CI automation | HTTP/gRPC APIs and quality gates |
| Apache JMeter | Test plans, protocol samplers, rich plugin ecosystem | HTTP and enterprise protocols |
| Gatling | Code-first scenarios, strong JVM ecosystem integration | Complex stateful HTTP flows |
| Locust | Python scenarios, user behavior modeling, distributed workers | Custom user journeys |
| Specialized SDK/benchmark tools | Measures database, storage, or messaging operations directly | Workloads poorly represented by HTTP |

When an application processes heavy asynchronous events, do not stop at sending HTTP requests. You may need a workload generator publishing messages directly to a test Pub/Sub topic alongside a verifier tracking consumer progress.

### Runner Placement Rules

- Place runners close to the workload to measure application latency, or at realistic client locations to measure end-to-end latency.
- Ensure runners have ample CPU, memory, and network bandwidth for target load.
- Never drive unbounded traffic from one undersized VM; saturated runner CPU skews latency numbers.
- Across multiple runners, synchronize clocks and tag results with the same `runId`.
- Account for runner, Cloud NAT, egress, load balancer, and target service costs.

Cloud Run itself can host controlled load-generation jobs, subject to request timeout, concurrency, quota, and cost constraints. Moving the generator elsewhere does not eliminate network and target-service charges.

## 7. k6 Script for a Read-Only API

The example below sends 20 iterations per second for 5 minutes to a side-effect-free read endpoint. Before running, point `BASE_URL` to an approved test environment.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_read: {
      executor: 'constant-arrival-rate',
      rate: 20,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 20,
      maxVUs: 100,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<600'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  const baseUrl = __ENV.BASE_URL;
  if (!baseUrl) {
    throw new Error('BASE_URL must point to an approved test service');
  }

  const response = http.get(baseUrl + '/health/ready', {
    timeout: '10s',
    tags: { operation: 'readiness' },
  });

  check(response, {
    'readiness returns 200': (r) => r.status === 200,
  });
}
~~~

Run:

~~~bash
k6 run --env BASE_URL="https://YOUR-STAGING-SERVICE-URL" load-read.js
~~~

Key takeaways:

- `constant-arrival-rate` controls **iterations started per second**; because each iteration here makes one request, it approximates RPS.
- `preAllocatedVUs` pre-warms VUs; `maxVUs` allows scaling up when iterations take longer.
- `http_req_failed` measures failed requests per k6 criteria; add business assertions via `check`.
- Thresholds can make k6 exit non-zero so pipelines block promotion.
- `/health/ready` is far lighter than real business endpoints; use it to learn load generation mechanics, **never to declare overall application capacity**.

### Authentication When Testing Private Cloud Run Services

When Cloud Run requires authentication, the test runner must obtain an **ID token with the matching audience** using an authorized workload identity. Pass the token via a runtime secret or protected environment variable; never hard-code tokens into scripts.

Example using a runner-supplied token:

~~~javascript
const response = http.get(__ENV.BASE_URL + '/api/orders/demo', {
  headers: {
    Authorization: 'Bearer ' + __ENV.ID_TOKEN,
  },
  tags: { operation: 'get_order' },
});
~~~

This snippet only illustrates the header, not a full k6 script. ID tokens are short-lived: long tests need a secure token refresh or re-issuance mechanism. If testing per-user authorization realism, do not substitute a single privileged token for all virtual users.

## 8. Designing Load Stages

A load test typically consists of four phases:

1. **Warm-up:** light traffic to stabilize runtimes, JIT compilation, caches, and connection pools.
2. **Ramp-up:** stepped load increases to observe where latency or resource utilization inflects.
3. **Steady-state:** sustained target load long enough to measure p95/p99, throughput, and error rate.
4. **Ramp-down/recovery:** reduce load and measure how quickly autoscaling, queues, and services return to baseline.

Illustrative test schedule:

| Phase | Illustrative Target Load | Duration | Purpose |
|---|---:|---:|---|
| Warm-up | 10 RPS | 3 minutes | Warm up service and dependencies |
| Ramp-up 1 | 30 RPS | 5 minutes | Check initial scaling response |
| Ramp-up 2 | 60 RPS | 5 minutes | Observe autoscaling behavior |
| Steady | 80 RPS | 15 minutes | Evaluate against SLO |
| Spike | 150 RPS | 1 minute | Test bursts and queuing |
| Recovery | 10 RPS | 5 minutes | Confirm clean return to stability |

Do not average spike and steady-state into a single number. A 1-minute spike is heavily shaped by cold starts and bursts, whereas steady-state reflects sustained capacity.

### k6 Ramp-Up Example by VU Count

~~~javascript
import http from 'k6/http';

export const options = {
  stages: [
    { duration: '2m', target: 10 },
    { duration: '5m', target: 30 },
    { duration: '5m', target: 60 },
    { duration: '5m', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<600'],
  },
};

export default function () {
  http.get(__ENV.BASE_URL + '/catalog', { timeout: '10s' });
}
~~~

This script controls **VUs**, not guaranteed 10/30/60 RPS. To enforce exact arrival rates, use `ramping-arrival-rate` with stages defined in iterations per time unit. Pick the executor matching the question you want answered.

### Controlling Coordinated Omission

Under a closed model, a slow server causes virtual users to issue fewer requests, throttling load right when the system struggles. Latency charts can look artificially rosy. For independent incoming traffic, arrival-rate executors mitigate this effect—though you must still monitor k6's `dropped_iterations`: if the runner lacks VUs to start iterations on schedule, actual load falls below target.

## 9. Load Testing Cloud Run

Cloud Run automatically scales instances based on request load and service settings. Adding instances increases request capacity, bounded by concurrency, CPU, memory, startup latency, max instances, and downstream bottlenecks.

### Parameters to Record

| Parameter | Impact |
|---|---|
| Request concurrency | Concurrent requests each instance handles |
| CPU and memory | Compute and memory headroom per instance |
| Min instances | Mitigates cold-start latency by keeping warm instances |
| Max instances | Bounds normal scale, cost, and downstream pressure |
| Request timeout | Maximum duration allowed per request |
| Startup behavior | Time required for containers to pass startup probes |
| Region and ingress | Network latency and inbound traffic path |
| CPU allocation | Affects background work and billing mode |

Inspect Cloud Run configuration before testing:

~~~bash
gcloud run services describe orders-api \
  --region="asia-southeast1" \
  --project="PROJECT_ID" \
  --format=yaml
~~~

This is a read-only inspection command. Never change max instances or concurrency mid-run without recording a separate baseline per configuration.

### Per-Instance Concurrency and JDBC Pools

A Cloud Run instance can serve multiple HTTP requests concurrently. If a Java app configures a HikariCP pool of 10 connections per instance, scaling to 30 instances creates potential demand approaching 300 connections—excluding other services or jobs.

This is a **configuration upper bound**, not a guarantee all connections stay open simultaneously. Still, it shows how service autoscaling can push Cloud SQL near its connection limit even while Cloud Run CPU has headroom.

Estimation formula:

\[
\text{PotentialConnections} =
  \text{Instances} \times \text{MaxPoolPerInstance}
\]

When sizing, also account for admin connections, migrations, read replicas, and other workloads sharing the database.

### What to Observe Under Load

- Service request count and request latency in Cloud Monitoring.
- Active instance count, cold starts, and startup delays.
- CPU/memory utilization, concurrency, and throttling.
- Contextualized HTTP 429, 503, 504, and client timeouts.
- Cloud SQL connection count, query latency, and DB CPU.
- Logs, traces, startup failures, and connection-pool timeouts.

Do not blame every 429/503 on autoscaling; they can originate from application rate limiters, Cloud Armor, quotas, or backing services. Separate errors by request-handling layer.

### Passing Criteria

Cloud Run passes the scenario when successful throughput meets target, p95/p99 and error rates meet SLO, business correctness holds, and autoscaling does not exhaust downstream dependencies. Measure cost per successful request, not only peak RPS.

## 10. Load Testing GKE

On GKE, capacity depends on Pod configuration, replica counts, node pools, resource requests/limits, Horizontal Pod Autoscaler (HPA), cluster autoscaler, and dependency capacity.

### Scaling Layers to Observe

1. **Application:** JVM threads, connection pools, GC, caches, and request efficiency.
2. **Pod:** CPU/memory utilization, restarts, readiness, `OOMKilled`, and CPU throttling.
3. **HPA:** current/desired replicas, CPU or custom scaling metrics.
4. **Scheduler:** Pods stuck `Pending` from insufficient CPU, memory, quotas, or topology constraints.
5. **Cluster autoscaler:** new nodes provisioned per configured bounds.
6. **Networking:** Services, ingress/load balancers, DNS, and network policies.
7. **Dependencies:** Cloud SQL, Pub/Sub, Storage, or external APIs.

Inspect cluster state before and during tests:

~~~bash
kubectl get deploy,hpa -n load-lab
kubectl get pods -n load-lab -o wide
kubectl describe hpa orders-api -n load-lab
kubectl get nodes
~~~

`kubectl top pods` and `kubectl top nodes` require an active metrics API and provide point-in-time snapshots rather than time-series dashboards.

### HPA and Pod Startup

HPA can scale up replicas when CPU rises, but:

- Under-sized or mismatched CPU requests distort scaling signals.
- New Pods spend time pulling images, starting up, passing readiness checks, and opening dependency connections.
- HPA cannot schedule nodes if the cluster is out of capacity.
- Cluster autoscaler can hit quotas, regional/zonal stockouts, or min/max node bounds.
- Workloads can show low CPU while bottlenecked on DB locks, I/O, or network waits.

If CPU stays below threshold while p99 climbs, inspect DB pools, queues, and thread starvation before simply adding replicas.

### Readiness and Traffic

During load tests, confirm new Pods receive traffic only after becoming Ready. Overly aggressive liveness probes can trigger restart loops under load. `PodDisruptionBudget` helps during voluntary disruptions, but does not cure overload or OOMs.

### HPA Can Amplify Database Pressure

For example, if each Pod holds a HikariCP pool of 12 connections and HPA scales to 25 replicas, potential connections reach 300. HPA protects the service against CPU exhaustion while potentially overloading Cloud SQL connections.

Tune pool size, request concurrency, queues, autoscaling caps, and deadlines together. Rapid scale-out can trigger a **connection storm** that drives system-wide p99 up.

## 11. Load Testing Java/Spring Boot Applications

For Java APIs, JVM and framework settings frequently become bottlenecks:

- JIT warm-up and class-loading time.
- Garbage collection pauses and allocation rates.
- Heap/non-heap memory vs. container memory limits.
- Servlet thread pools or reactive event loops.
- HTTP client connection pools and keep-alive settings.
- HikariCP max pool size, acquisition timeouts, and max lifetime.
- Database transaction duration and lock contention.
- JSON serialization, payload compression, and object allocation.
- Retry budgets, circuit breakers, and downstream timeouts.

### Instrumentation

Micrometer, OpenTelemetry, and Cloud Monitoring help measure:

| Metric | Meaning |
|---|---|
| HTTP server request duration | Application request latency |
| JVM heap usage / GC pauses | Memory pressure and garbage collection overhead |
| Executor active/queued tasks | Whether thread pools are saturating |
| HikariCP active/idle/pending connections | Whether the app is waiting for DB connections |
| DB query duration | Which queries slow down under load |
| HTTP client duration | Which downstream dependencies add latency |
| Retry attempts/timeouts | Whether retries are amplifying traffic |

Aggregate metrics by route template such as `/orders/{id}`, never by raw URLs containing millions of IDs. Never attach user IDs, request IDs, or emails as metric labels due to cardinality explosion and privacy risks.

### Correlating Logs and Traces

A slow p99 request trace might show:

1. 10 ms in controller routing.
2. 550 ms waiting to acquire a JDBC connection.
3. 50 ms executing the SQL query.
4. 20 ms serializing and returning the response.

Looking only at query execution time would suggest the database is fine. Connection acquisition wait time and pool saturation are the real bottleneck. Separate wait time from execution time.

### Do Not Optimize Based on a Single Number

A p95 improvement after bumping CPU might reflect warmer caches, a smaller dataset, or transient network variance. Run multiple iterations with identical data and environments, record variance, and compare apples to apples before concluding.

## 12. Cloud SQL and Read/Write Load Testing

Applications backed by Cloud SQL must load test both API and database behaviors, because stateless API scaling does not imply transactional database scaling.

### Dataset Design

- Use schemas and migrations matching production.
- Seed enough rows and realistic key distributions so indexes and query planners behave realistically.
- Match the target read/write ratio.
- Exercise both common queries and expensive queries.
- Provide safe cleanup, or rebuild lab databases from synthetic snapshots/datasets.

Never run overwrite or bulk-delete performance tests against production Cloud SQL.

### Metrics and Bottleneck Signals

| Metric | What to Inspect on Spikes |
|---|---|
| Database CPU utilization | Heavy queries, missing indexes, CPU saturation |
| Memory usage | Buffer/cache pressure |
| Active connections | Pool sizing, connection leaks, autoscaling storms |
| Query latency | SQL plans, locks, indexes, storage I/O |
| Lock waits/deadlocks | Long transactions or row contention |
| Disk IOPS/latency | I/O saturation and full table scans |
| Replication lag | Whether read replicas keep up with write load |
| JDBC pool pending | Application threads waiting on connections |

### Testing Contention Scenarios

For example, two concurrent requests creating orders with the same idempotency key. Tests must verify:

- Only one primary record takes effect.
- The duplicate request receives the expected result or conflict status per API contract.
- Two business events are not emitted if exactly-once business effect is required.
- Concurrent requests never leave stalled transactions.

If using the Cloud SQL Auth Proxy or JDBC connector, test with the exact production connection mechanism. Testcontainers PostgreSQL helps check SQL/transactions locally, but **does not prove** production Cloud SQL connection limits, networking, IAM DB auth, or availability.

### Do Not Use Connection Count as the Sole SLO

A database can hold many idle connections yet stall on a single table lock or slow query. Combine latency, throughput, query plans, and transaction behavior.

## 13. Pub/Sub and Asynchronous Load Testing

In event-driven architectures, publisher throughput alone cannot prove the system handles the load. Consumers may lag behind producers, causing unbounded backlog growth.

### Metrics to Measure

- Publish success rate and publish latency.
- Message publish, receive, and ack rates.
- `num_undelivered_messages` or equivalent backlog metric.
- Age of oldest unacknowledged message.
- Consumer processing duration and concurrency.
- Redelivery, retry, nack, and dead-letter counts.
- Fraction of messages producing accurate business side effects.
- End-to-end time from event publish to business completion.

### Backlog Example

Suppose producers publish 500 messages/second for 10 minutes while consumers sustain 400 messages/second. If those rates hold without throttling, the backlog grows by roughly 100 messages/second—reaching 60,000 messages after 10 minutes.

This is a capacity illustration; actual backlog depends on batching, retries, redeliveries, subscriber acks, and processing variance.

### Evaluating Backlog Drain

A drain test includes:

1. Recording initial message count and backlog age.
2. Publishing synthetic messages tagged with a `runId`.
3. Monitoring receive, ack, and business completion rates.
4. Stopping the publisher after a fixed duration.
5. Continuing observation until backlog returns to baseline.
6. Verifying all event IDs processed cleanly.
7. Inspecting duplicate processing and dead-letter topics.

Do not clean up a subscription by purging the entire backlog when you need verification evidence. Use dedicated subscriptions or prefixes/`runId` to isolate test runs.

### Exactly-Once Business Effect and Idempotency

In many Pub/Sub setups, messages can be redelivered. Load scenarios should deliberately inject duplicate logical events and verify consumers never commit duplicate records. Correctness means **one business side effect per event ID**, not necessarily one in-process callback invocation.

Never declare a load test successful based solely on published message counts without verifying the downstream database, as publishers may "succeed" while consumers drown in backlog.

## 14. Cloud Storage, Firestore, and Other Data Services

Each data service has distinct throughput, latency, quota, and billing characteristics. Scenarios must reflect actual operations instead of reusing a generic HTTP GET script.

| Service | Load Scenario | What to Monitor |
|---|---|---|
| Cloud Storage | Uploads/downloads across object sizes, range reads, metadata reads | Request latency, errors, egress, bytes/s, and object generations |
| Firestore | Transactional reads/writes, queries, and document contention | Latency, errors, quotas, indexes, contention, and retries |
| Bigtable | Key-distributed reads/writes, range scans | Node CPU, latency, hotkeys, and throughput |
| Spanner | Transactional reads/writes, queries, and commits | CPU, transaction aborts/retries, latency, locking |
| BigQuery | Analytical queries over representative datasets | Slot usage, query latency, bytes processed, and cost |
| Cloud SQL | Read/write transactions, connection pooling | DB CPU, locks, I/O, pool waits, and query latency |

### Cloud Storage

- Test both small and large objects, not just tiny payloads.
- Measure byte/s throughput separately from metadata operation latency.
- For write tests, use a lab bucket and unique object prefixes.
- On overwrites, apply generation preconditions where business rules forbid clobbering.
- Account for cross-region egress when clients and buckets sit in different locations.

### Firestore

- Use sufficiently large lab datasets and production-like indexes.
- Avoid artificial hotspots concentrating all writes onto a single document/key.
- Measure contention and transaction retries, not only successful write counts.
- Test quotas, IAM, and networking on the live service; emulators do not fully simulate performance, quotas, or operational semantics.

### BigQuery

BigQuery is an analytical warehouse, not a low-latency OLTP database for tiny per-request queries. Load tests must define query concurrency, scan size, partition pruning, caching, and slot capacity. Results vary with query cache and dataset size; always record whether caching was enabled.

BigQuery tests can incur major costs depending on project billing models. Enforce query limits, budgets, and test datasets; never run unbounded scans against production tables to probe throughput.

### Bigtable / Spanner

For Bigtable, row-key distribution governs hotspots and throughput. For Spanner, transaction contention, aborts/retries, and placement affect latency. Use workload generators matching real client libraries and data distributions, explicitly measuring errors and retries.

## 15. Dashboards and Multi-Layer Analysis in Cloud Monitoring

Load testing must combine generator metrics with Cloud Monitoring, Cloud Logging, and Cloud Trace. Never draw conclusions from a k6 report alone.

A minimal dashboard should cover:

| Group | Signals | How to Read |
|---|---|---|
| Client | Offered RPS/iteration rate, achieved RPS, dropped iterations | Did the generator actually deliver the intended load? |
| API | Request count, 5xx, p95/p99 latency | Does the service meet SLOs? |
| Compute | Instance/Pod counts, CPU, memory, throttling | Autoscaling behavior and saturation |
| Database | Connections, CPU, query latency, lock waits | Data-tier bottlenecks |
| Messaging | Publish rate, backlog, oldest unacked age | Are consumers keeping pace? |
| Business | Orders created, duplicate IDs, completion rate | Are business outcomes accurate? |
| Cost | Instance/CPU time, egress, DB charges, API usage | Cost per successful request/transaction |

### Correlating Results by Run ID

Store `runId` in test report metadata and, where appropriate, in a non-sensitive request header:

~~~text
X-Test-Run-Id: load-2026-11-19-a1b2
~~~

Never use a near-unique `runId` as a Prometheus metric label on every production request, as it causes cardinality explosions. Instead, attach `runId` to sampled logs/traces while aggregating metrics by route or operation.

### Reading the Timeline

Track key timestamps:

- T0: warm-up begins.
- T1: load ramps up.
- T2: CPU/latency or queues begin climbing.
- T3: autoscaler adds instances/Pods.
- T4: steady load or system hits saturation limits.
- T5: load stops; recovery measured.

If p95 climbs before CPU climbs, inspect DB locks, networking, or connection pools. If API latency drops after scale-out while the Pub/Sub backlog keeps growing, the asynchronous consumer pipeline lacks capacity.

## 16. Evaluating Results and Identifying Breaking Points

Never advertise "handles 1,000 RPS" if error rates spike or data consistency goes unverified at that rate. A breaking point is typically the load level where any service criterion is violated.

Hypothetical illustrative report:

| Target Load | Successful RPS | p95 | 5xx Errors | Verdict |
|---|---:|---:|---:|---|
| 25 RPS | 25 | 180 ms | 0% | Pass |
| 50 RPS | 49.8 | 260 ms | 0.1% | Pass |
| 100 RPS | 98 | 520 ms | 0.8% | Compare against SLO |
| 150 RPS | 130 | 1,400 ms | 8% | Fail |
| Recovery | Returned to baseline | 240 ms | 0% | Verify data and queues |

These numbers only illustrate how to read the table and do not represent default Cloud Run/GKE capacity.

### Responsible Reporting Practices

- Compare only runs sharing comparable configuration and datasets.
- Report warm-up, steady-state, spike, and recovery separately.
- Distinguish **offered load** from **achieved load**.
- Report successful requests, not only total requests sent.
- Categorize errors by layer: 4xx from test data, 5xx, quotas, timeouts, DB errors.
- Correlate request latency with database/queue metrics and replica counts.
- Verify zero unintended business side effects.
- Document untested limits or unsimulated conditions.

When a test is bottlenecked by the generator, client network, or test quotas, never report that ceiling as the application's capacity limit.

### Defining Pass / Fail / Inconclusive

Example definitions:

- Pass: sustains 80 successful RPS at steady-state, p95 ≤ 600 ms, error rate ≤ 0.5%, zero duplicate orders, and backlog returns to baseline within 5 minutes post-test.
- Fail: any critical threshold is violated.
- Inconclusive: generator lacked capacity, environment changed mid-run, or required metrics were missing.

Thresholds must be approved by application/SRE teams prior to running. Never relax thresholds after viewing results just to mark a run Pass.

## 17. Integrating Load Testing into CI/CD

A structured pipeline runs checks from cheapest to costliest:

1. Unit, integration, and contract tests.
2. Build image, scan, and record image digest.
3. Deploy to staging with production-like configuration.
4. Run smoke tests and short load tests at safe traffic levels.
5. Verify SLOs, data correctness, and cost guardrails.
6. Approve release or block promotion.
7. After production deploy, monitor canaries and production SLIs.

With Cloud Build/Cloud Deploy, bind test results to commit SHA, image digest, target, revision, and `runId`. Whenever a new image is built, never reuse old load test results as evidence for the new artifact.

### Quality Gates with k6

k6 exits non-zero when thresholds fail. Use that exit code in CI to block promotion. However, client-side thresholds do not replace checking resource saturation, queue backlogs, and data consistency in Cloud Monitoring.

Expensive scenarios such as stress tests or long soak tests should run on a schedule or ahead of major infrastructure changes rather than on every pull request.

### Controlling Baseline Changes

After changing:

- Cloud Run concurrency or CPU.
- GKE HPA targets or Pod resource requests.
- Cloud SQL tier, indexes, or pool size.
- Region, load balancer, or caching.
- JVM or client SDK versions.

Re-run the baseline under matching data and conditions, archive old and new configurations, and compare p95, throughput, error rate, and cost.

## 18. Practical Scenario: Orders API on Cloud Run, Worker on GKE

Suppose the system consists of:

- Java/Spring Boot `orders-api` on Cloud Run.
- Cloud SQL for PostgreSQL storing orders and outbox records.
- Pub/Sub delivering `OrderCreated`.
- Java worker on GKE confirming orders.
- Cloud Storage storing PDF invoices.
- Cloud Monitoring, Cloud Logging, and Cloud Trace for observability.

Hypothetical targets: sustain 80 order-creation requests/second for 15 minutes; API p95 under 600 ms; failure rate under 0.5%; zero duplicate orders; backlog drains within 5 minutes after load stops.

### Step 1 — Prepare the Test Project

- Provision an isolated staging environment with Cloud Run, GKE, Cloud SQL, Pub/Sub, and Storage.
- Use a database populated with a synthetic dataset and production-like indexes.
- Use a load-test service account granted permission to invoke APIs and read test results.
- Never emit events to production consumers or live payment gateways.
- Confirm budgets, quotas, and cleanup windows.
- Record image digest, revision, Cloud Run/GKE settings, and DB tier.

### Step 2 — Design the Scenario

- Generate `POST /orders` requests with valid synthetic payloads.
- Give each logical order a unique idempotency key.
- Include a slice of retry requests sharing the same key to verify deduplication.
- Track API responses and order IDs.
- Afterward, verify the worker transitions status to `CONFIRMED`.
- Verify invoices appear under the `runId`-scoped prefix.

### Step 3 — Run Baseline and Ramp Load

1. Run a 5 RPS smoke test to verify auth and test data.
2. Warm up at 10 RPS.
3. Step up to 30 and then 60 RPS.
4. Hold 80 RPS for 15 minutes.
5. If approved, run a brief spike above baseline.
6. Ramp down and keep monitoring to measure backlog drain and recovery.

Do not escalate to stress testing if the database is already nearing connection limits or consumer backlog is growing uncontrollably.

### Step 4 — Multi-Layer Measurement

- k6: started/succeeded requests, p95/p99, timeouts, dropped iterations.
- Cloud Run: concurrency, instances, CPU, memory, 429/5xx.
- Cloud SQL: connections, query latency, lock waits, CPU.
- Pub/Sub: oldest unacked age, backlog, and ack rate.
- GKE: consumer replicas, Pod readiness, JVM metrics, and HPA.
- Business: unique order count, duplicate event IDs, verified invoices.

### Step 5 — Analysis

For example, the API sustains 80 RPS while the backlog grows steadily. That means the HTTP tier has sufficient immediate capacity, **not that the overall system meets requirements**. Inspect consumer throughput, transaction locks, JDBC pools, or GKE autoscaling.

If Cloud SQL connections climb in lockstep with Cloud Run instances, lower pool size per instance, cap concurrency, or tune scaling; re-run tests to verify the fix.

### Step 6 — Wrap-Up

- Stop all load generators.
- Wait for queues to return to baseline or drain isolated test backlogs.
- Reconcile all test orders and corresponding invoices.
- Clean up only resources tagged with `runId`.
- Archive reports, dashboard snapshots, configs, and conclusions.
- Open action items with owners and deadlines for any discovered bottlenecks.

## 19. Troubleshooting Unexpected Results

| Symptom | Hypothesis | Where to Check |
|---|---|---|
| Achieved RPS lower than target | Generator lacks VUs, CPU, or network | k6 `dropped_iterations`, VU usage, runner CPU |
| High p95 with low app CPU | DB pool waits, locks, network, external APIs | Traces, HikariCP pending, DB metrics |
| 429 spikes during bursts | Rate limits, capacity/quotas, or upstream limits | Cloud Run/load balancer/app logs, quotas |
| 503 rises during ramp-up | Startup, readiness, backend health, or dependencies | Cloud Run revision / GKE Pod events |
| Cloud Run instances rise, DB errors rise | Connection storm or DB saturation | `pool * instances`, Cloud SQL connections |
| GKE HPA scales up but Pods stay Pending | Cluster lacks nodes, quota, or topology capacity | Scheduler events, cluster autoscaler |
| Pub/Sub publish steady, backlog grows | Low consumer throughput | Ack rate, oldest unacked age, GKE worker |
| Fast initially, slows over time | Memory leak, pool leak, cache, GC, or throttling | JVM, connections, GC, DB |
| High variance across runs | Unstable dataset, caching, runner, or region | Compare configs and test ordering |
| Duplicate records created | Broken idempotency or retry handling | Unique constraints, event IDs, transaction logs |

Change only one variable group per test cycle whenever possible. Establish a fresh baseline per change and compare under identical conditions.

## 20. Load Test Execution Checklist

### Before Running

- [ ] Load targets, SLIs/SLOs, and stop conditions are approved.
- [ ] Target endpoints, project, region, and test resources are verified.
- [ ] Operators and service owners know the test schedule.
- [ ] Synthetic data, `runId`, and safe cleanup are prepared.
- [ ] Load generators have sufficient capacity and connectivity.
- [ ] Budgets, quotas, rate caps, and duration limits are enforced.
- [ ] Cloud Run/GKE/DB configurations are recorded as baseline.
- [ ] Dashboards, logs, and traces are ready.

### During Execution

- [ ] Record start timestamps for each load stage.
- [ ] Measure offered load, achieved throughput, p95/p99, and error rate.
- [ ] Monitor CPU/memory, autoscaling, instances/Pods, and quotas.
- [ ] Monitor Cloud SQL pools, transactions, and locks.
- [ ] Monitor Pub/Sub backlogs and duplicate processing.
- [ ] Verify business data correctness, not just HTTP 200.
- [ ] Halt or throttle load immediately if any guardrail trips.

### After Execution

- [ ] Stop generators and confirm test traffic has ceased.
- [ ] Confirm queues and resources returned to baseline.
- [ ] Reconcile and clean up scoped test data.
- [ ] Link results to commit SHA, image digest, and configuration.
- [ ] Classify Pass, Fail, or Inconclusive against pre-approved thresholds.
- [ ] Report throughput, latency, errors, saturation, and cost.
- [ ] Assign owners, remediation plans, and re-test schedules for bottlenecks.

Load testing on GCP is not simply cranking up requests/second until the API fails. A rigorous test models real user behavior, observes Cloud Run, GKE, and data-service layers together, protects the test environment, and verifies business correctness and recovery. When SLOs, guardrails, load scenarios, and dashboards align, teams make capacity and release decisions grounded in data rather than guesswork.

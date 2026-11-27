# Load Testing Against Real Services Before Tuning Production Configuration

## Learning objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot connects to managed databases, caches, messaging, object storage, and compute on AWS, Azure, and Google Cloud. Each service has its own network latency, resource limits, quotas, autoscaling behavior, and billing model. A configuration that performs well against mocks or emulators may not deliver the same performance when calling real managed services.

This lesson shows how to run controlled load tests before changing production configurations:

1. Building a workload model from real traffic, user journeys, data profiles, and SLOs.
2. Provisioning a pre-production environment with real managed services whose region, networking, tier, and security closely match production.
3. Distinguishing smoke, baseline, load, stress, spike, soak, and breakpoint tests.
4. Using k6, JMeter, or Gatling to control arrival rate, concurrency, and test duration.
5. Measuring client-side metrics, Spring Boot metrics, and per-service managed metrics simultaneously.
6. Pinpointing bottlenecks across the application, connection pool, database, cache, queue, network, or load generator.
7. Testing one configuration change at a time, comparing identical workloads, and checking latency, reliability, and cost.
8. Managing quotas, budgets, test data, permissions, and stop conditions to protect systems.
9. Rolling out validated configurations via canary/gradual rollout with a rollback plan.

## 1. Why load test against real managed services?

### 1.1. Mocks and emulators do not represent production performance

Unit tests use mocks to verify service logic. Local emulators or container databases help verify APIs, schemas, and integration behavior. Those tools are valuable, yet cannot faithfully reproduce:

- Latency from the application to managed endpoints over VPC/VNet, private service access, or public endpoints.
- TLS handshakes, DNS, connection establishment, and connection reuse.
- Provider authentication, IAM, token refreshes, and authorization.
- CPU, memory, IOPS, connection limits, and throughput of actual managed tiers.
- Autoscaling, cold starts, instance concurrency, and scale-out times.
- Rate limits, quotas, throttling, and retry behavior.
- Replication lag, failover, backups, maintenance, and network behavior.
- Request, compute, storage, egress, and observability costs.

For example, a mock repository may return in 1 ms. A real managed database incurs connection establishment, pool wait, query execution, data transfer, and TLS overhead. Benchmarking only mocks leaves teams blind to real connection pool limits or database tier ceilings.

### 1.2. Measuring both the application and backend services

~~~mermaid
flowchart TD
    GEN["Load generator<br/>k6 / JMeter / Gatling"] --> LB["Ingress / Load Balancer / API Gateway"]
    LB --> APP["Spring Boot instances"]
    APP --> DB["Managed database"]
    APP --> CACHE["Managed cache"]
    APP --> MSG["Managed messaging"]
    APP --> OBJ["Object storage"]
    APP --> THIRD["External service"]
    APP --> OBS["Micrometer / OpenTelemetry"]
    DB --> MON["Cloud monitoring"]
    CACHE --> MON
    MSG --> MON
    OBJ --> MON
    OBS --> MON
    GEN --> CLIENT["Client metrics<br/>latency / throughput / errors"]
~~~

Test results must reveal where requests slow down. Looking only at client response times is insufficient to decide whether to add Spring Boot CPU, upgrade the database tier, or tune connection pools.

### 1.3. Key principles

- Use real managed services in final integration performance testing.
- Use a dedicated environment configured close to production; never slam customer-facing production with heavy load tests by default.
- Simulate realistic user behavior and data rather than hammering one endpoint with an identical payload.
- Measure the client, application, dependencies, and load generator together.
- Lock down SLOs and acceptance criteria before running.
- Change only one configuration group at a time so you know what caused the outcome.
- Record application version, config, region, resource types, and test data for repeatability.

## 2. Building a workload model

### 2.1. Starting from user journeys

A reservation system might include these flows:

| Flow | Steps | Dependency load |
| --- | --- | --- |
| List view | API → database/cache → response | Read-heavy, cache hits/misses |
| Detail view | API → database → object storage | Lookup by ID, metadata fetch |
| Search | API → database/search service | Query/filter/sort |
| Create reservation | API → database transaction → outbox | Reads + writes + locks |
| Payment | API → payment provider → database | Network latency, retries |
| Document upload | API → object storage → metadata database | Upload bytes, metadata write |
| View reports | API → analytics database | Heavy queries, large reads |

Not all requests carry equal cost. A test calling only `GET /health` cannot represent reservation creation, payment, or file upload traffic.

### 2.2. Traffic mix and think time

Estimate request proportions from access logs, analytics, or validated business assumptions.

Example composite workload:

| Flow | Request share | Notes |
| --- | ---: | --- |
| Browse/search | 45% | Read-heavy |
| Product/detail | 25% | Cacheable |
| Reservation create/update | 15% | Transactions and contention |
| Payment status | 10% | Database and provider calls |
| Report/export | 5% | Heavy queries, large payloads |

These percentages are illustrative only. Substitute your own system's distribution.

Think time is the pause while a user reads or waits before the next action. Do not generate traffic in tight back-to-back loops if real users pause between actions. For machine-to-machine APIs or webhooks, arrival rates may be continuous with zero think time.

### 2.3. Arrival rate vs. concurrency

Two common load models:

- **Closed workload model:** a fixed number of virtual users; each user sends a request, waits for the response, and only then starts the next iteration. When the system slows down, request rate drops automatically.
- **Open workload model:** incoming request rate is controlled independently of response time. Suited for simulating systems receiving traffic at a fixed arrival rate.

When using a closed model to find limits, rising latency can inadvertently reduce sent requests and mask overload. For APIs receiving continuous traffic, an open model like k6's `arrival-rate` executor controls requests/second much more accurately.

Use Little's Law to estimate concurrent in-flight requests:

\[
L = \lambda \times W
\]

Where `L` is average in-flight requests, `lambda` is arrival rate (requests/second), and `W` is average processing time (seconds). For instance, 80 requests/second with an average 0.25-second duration implies roughly 20 in-flight requests at steady state. This is an average estimate and does not replace p95/p99 and burst measurements.

### 2.4. Data profile must resemble production

Test data should reflect:
- Row/document counts and table sizes.
- Ratio of hot keys to rare keys.
- Duplication levels and cardinality.
- Data distribution across tenants, statuses, and time.
- Indexes, partitions, clustering, and schema.
- Object, message, and response sizes.
- Expected cache hit ratios.

An empty database yields overly optimistic results. Tiny indexes fitting entirely in memory may fail to reflect production behavior. Use synthetic data or anonymized snapshots matching production volume and distribution.

### 2.5. Defining SLOs and acceptance criteria

Before testing, document targets:

| Metric | Example acceptance criteria | How determined |
| --- | --- | --- |
| Error rate | Under 1% at expected peak | SLO / API contract |
| p95 latency | Under 500 ms for browse | Product SLO |
| p99 latency | Under 1.2 s for browse | Tail latency objective |
| Throughput | Sustain 100 requests/s | Traffic forecast |
| Database connections | Below 80% of safe limit | Database capacity |
| Queue backlog | No unbounded growth after peak | Processing SLA |
| CPU/memory | Headroom left to scale | Capacity policy |
| Cost per 1,000 requests | Within budget | Unit economics |

Numbers in this table are examples only. Never copy these thresholds to production without grounding them in your real system's SLOs, UX, quotas, and costs.

## 3. Preparing a pre-production environment

### 3.1. Use real managed services, isolated from production

A staging/performance environment should have:
- Dedicated AWS account, Azure subscription, or Google Cloud project.
- VPC/VNet, subnets, firewalls, private endpoints, and DNS mirroring production.
- Real managed databases, caches, queues, and object storage.
- Matching engine/version, tier, or machine family close to production.
- Same geographic region and network path as production application runtimes.
- Equivalent authentication and IAM using dedicated test service accounts/roles.
- Identical indexes, schemas, partitions, and connection pool structures.
- Autoscaling, min/max instances, and timeouts near target settings.

If staging is scaled down relative to production, results remain useful for catching regressions, yet production capacity cannot be extrapolated linearly. Some services exhibit non-linear scaling thresholds, quotas, or topology differences.

### 3.2. Use real managed services for every dependency

| Dependency | Real resources to test against | What to observe |
| --- | --- | --- |
| Relational database | Cloud SQL, Amazon RDS/Aurora, Azure SQL | Query latency, CPU, IOPS, connections, locks |
| NoSQL database | Firestore, DynamoDB, Cosmos DB | Request latency, throughput, throttling, hot keys/partitions |
| Cache | Memorystore, ElastiCache, Azure Managed Redis | Hit ratio, latency, memory, connections, evictions |
| Messaging | Pub/Sub, SQS/SNS, Service Bus | Publish/consume rates, backlog, oldest message, retries |
| Object storage | Cloud Storage, S3, Blob Storage | Throughput, latency, request rate, egress |
| Compute | Cloud Run/GKE, ECS/EKS, App Service/AKS | Startup, CPU, memory, concurrency, instance count |

Emulators remain suitable for functional integration tests. Use real managed services when measuring networking, tier capacity, authentication, quotas, scaling, and provider behavior.

### 3.3. Keep topology close to production

Differences that can invalidate tests:

- Load generator on the same host or zone as the database when production crosses regions.
- Using public endpoints in staging vs. private endpoints in production.
- Using a significantly larger or smaller database tier.
- Disabling TLS or using different credentials than runtime.
- Leaving autoscaling disabled when production enables it.
- Bypassing gateways, WAFs, load balancers, or service meshes.
- Using a dataset far smaller than production.
- Testing against pre-warmed caches when production frequently cold-starts.

Document topology and every discrepancy. Where full parity is infeasible, mark results as bounded rather than extrapolating blindly.

### 3.4. Data safety and permissions

- Use synthetic or anonymized data only.
- Provision dedicated test tenants and users.
- Use least-privilege service accounts/roles.
- Never use production tokens or personal secrets.
- Tag request headers, logs, and metrics with a test run ID where possible.
- Never hit real payment or destructive endpoints without sandbox/test modes.
- Prepare cleanup jobs for test data.
- Configure rate limits, quotas, and budget alerts before ramping load.

### 3.5. Verify limits and budgets before testing

Load tests can generate substantial charges on both generators and target services. Before running:
1. Check service quotas, request limits, database connection limits, and autoscaling caps.
2. Identify quotas that may need increases ahead of testing.
3. Estimate test duration and load volume.
4. Set budget alerts and metric alarms.
5. Define stop conditions when cost, error rate, or resource utilization crosses thresholds.
6. Ensure operations teams know the test window and someone is actively watching.

Google Cloud recommends reviewing quotas and costs and configuring billing budget alerts when preparing load tests for critical workloads. [Google Cloud conduct load testing guide](https://docs.cloud.google.com/support/docs/peak-events/conduct-load-testing).

## 4. Types of load tests

| Test type | Objective | Load shape | Question to answer |
| --- | --- | --- | --- |
| Smoke | Verify script and environment work | Very few VUs/requests | Do endpoints, auth, and data work? |
| Baseline | Measure performance at low/typical load | Steady load | What are normal latency and resource usage? |
| Load | Validate expected peak | Ramp to expected peak and hold | Do we meet SLOs at expected load? |
| Stress | Find limits | Ramp progressively past peak | Where is the first bottleneck? |
| Spike | Test traffic surges | Very rapid load increase | How do autoscaling, queues, and cold starts react? |
| Soak | Test long-term stability | Hold steady load for hours | Are there memory leaks, connection leaks, or growing backlogs? |
| Breakpoint/capacity | Find max load meeting SLOs | Step up until thresholds fail | What is safe capacity and headroom? |
| Failover/resilience | Test behavior under degraded dependencies | Controlled load + injected faults | Do retries, timeouts, and failover preserve SLOs? |

### 4.1. Smoke test

Run a handful of requests to verify the load generator reaches endpoints, authentication succeeds, test data exists, responses match schemas/status codes, scripts do not mutate unintended data, and metrics/traces record properly. If smoke testing fails, do not proceed to heavy load.

### 4.2. Baseline test

Run at a repeatable low or moderate load. Record throughput, p50/p95/p99, error rate, app CPU/memory, database/cache/queue metrics, and cost or usage units. The baseline anchors every future comparison. Reuse the exact same script, data seed, and duration.

### 4.3. Load test

Ramp up to expected peak and hold long enough for autoscaling and connection pools to stabilize. Never draw conclusions from a brief few-second ramp-up. Watch scale-out time, queue backlogs, and tail latency.

### 4.4. Stress and breakpoint tests

Step up beyond projected peak until p95/p99 breaches SLOs, errors/throttling climb, queue backlogs grow monotonically, CPU/memory/connections/IOPS saturate, autoscaling hits max instances, or costs exceed acceptable limits. Halt when safety stop conditions fire. The goal is discovering limits and failure modes, not breaking the environment.

### 4.5. Spike test

Simulate abrupt surges such as campaigns, email blasts, or live events. Monitor cold starts, pending requests, instance creation, connection storms, cache stampedes, queue backlogs, and retry bursts.

Cloud Run documentation provides guidance on testing container concurrency, cold starts, and scale-out before applying results to production tuning. [Cloud Run load testing best practices](https://docs.cloud.google.com/run/docs/about-load-testing).

### 4.6. Soak test

Hold expected load over an extended duration to uncover memory leaks, unreturned pool connections, unbounded cache key growth, falling-behind queue consumers, token-refresh or scheduled-job spikes, rising log/metric volume costs, and creeping disk/storage usage.

Do not watch average CPU alone. Track trends in memory, open connections, thread counts, queue age, and error rates over time.

## 5. Using k6 for controlled workloads

### 5.1. Why control load rate?

The load generator must explicitly govern requests initiated per second, virtual users, ramp-up/hold/ramp-down durations, think time, endpoint mix, and when to abort if thresholds fail.

Google Cloud notes not to use traffic sources with uncontrolled rate and concurrency as load generators. A message broker like Pub/Sub is unsuitable for generating test traffic unless arrival rates and client counts are tightly controlled. [Cloud Run load testing best practices](https://docs.cloud.google.com/run/docs/about-load-testing).

### 5.2. k6 arrival-rate example

The script below exercises a catalog GET endpoint. `BASE_URL`, `API_TOKEN`, and `TEST_RUN_ID` are passed via environment variables; never commit secrets into scripts.

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    catalog_load: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 100,
      stages: [
        { target: 10, duration: '2m' },
        { target: 25, duration: '5m' },
        { target: 40, duration: '5m' },
        { target: 0, duration: '1m' },
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1200'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  const response = http.get(
    __ENV.BASE_URL + '/api/v1/catalog?limit=20',
    {
      headers: {
        Authorization: 'Bearer ' + __ENV.API_TOKEN,
        'X-Test-Run': __ENV.TEST_RUN_ID,
      },
      tags: { endpoint: 'catalog-list' },
    },
  );

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response is JSON': (r) =>
      r.headers['Content-Type']?.includes('application/json'),
  });

  sleep(1);
}
~~~

The 500 ms, 1,200 ms, and 1% thresholds here are illustrative. Replace them with your real API's SLOs.

Run the script:

~~~bash
k6 run \
  -e BASE_URL=https://staging-api.example.internal \
  -e API_TOKEN="$PERF_TEST_TOKEN" \
  -e TEST_RUN_ID=perf-2026-11-24-01 \
  catalog-load.js
~~~

In CI, pull tokens from a secret store or CI secret variable. Never print tokens to logs.

### 5.3. Arrival rate, VUs, and dropped iterations

With `arrival-rate` executors, k6 tries to start iterations at the configured pace. When insufficient VUs exist to run iterations, `dropped_iterations` rises.

When you see dropped iterations:
- Inspect `maxVUs` / `preAllocatedVUs`.
- Inspect load generator CPU/memory/network.
- Check whether iteration duration rose because the SUT slowed down.
- Do not raise VUs blindly; if the generator itself is congested, results do not reflect real service capacity.

k6 scenarios let you compose multiple independent load profiles. [k6 scenarios](https://grafana.com/docs/k6/latest/using-k6/scenarios/).

### 5.4. Checks vs. thresholds

- `check()` verifies response conditions or business assertions per request.
- `thresholds` define pass/fail criteria for the entire test run.

A failed check does not automatically fail the k6 process exit status unless backed by a threshold. Always define thresholds on error rate, latency, and check rate. [k6 thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/).

### 5.5. Separating scenarios by user journey

A realistic test combines multiple scenarios: browse/search, detail reads, create/update with unique test data, object upload/download, message publish/consume, and reporting queries.

Tag endpoints and scenarios so latencies stay separated. Never let one fast endpoint mask a slow checkout endpoint in an aggregate average.

### 5.6. Write tests and cleanup

For mutating APIs:
- Generate a unique test ID per iteration.
- Supply idempotency keys where supported.
- Write strictly to a dedicated test tenant/dataset.
- Never trigger real payments or send emails/SMS to real customers.
- Enforce cleanup or TTLs on test data.
- Monitor record growth across databases and storage.
- Keep rolled-back transaction tests separate from real-commit tests, as they produce different load profiles.

## 6. Testing tools and selection

| Tool | Strengths | Best fit |
| --- | --- | --- |
| k6 | Script-as-code, arrival rate, thresholds, CI integration | API load testing, automated regressions |
| Apache JMeter | GUI, thread groups, broad protocol support | Teams with existing JMeter plans needing complex protocols |
| Gatling | Code-based scenarios, reports, high-throughput testing | Service/API testing with versionable scenarios |
| Azure Load Testing | Managed test execution, Azure Monitor integration | Azure workloads or managed load testing |
| Browser-based load tools | Measures real browser UX | Small numbers of browser VUs paired with protocol load |

No tool generates valid load if the scenario itself is wrong. Pick tools based on supported protocols, rate control, generator capacity, and team operational familiarity.

You can combine protocol-level tests for the bulk of traffic with fewer browser-based VUs to observe browser rendering experience. [k6 load testing guide](https://grafana.com/docs/k6/latest/testing-guides/load-testing-websites/).

## 7. Measuring client-side and server-side metrics

### 7.1. Client-side metrics

From k6/JMeter/Gatling, collect request rate (RPS), throughput bytes/second, p50/p90/p95/p99 latency, error rate by status and endpoint, timeouts/connection errors, check failures, dropped iterations, payload sizes, and DNS/connect/TLS/TTFB where exposed.

Use percentiles rather than averages alone. An average can look healthy while a small slice of requests suffers severe p99 tail latency.

### 7.2. Spring Boot metrics

Spring Boot Actuator and Micrometer expose:
- HTTP server request counts and latency.
- JVM heap/non-heap memory and GC pauses.
- Thread counts and executor queues.
- HikariCP active/idle/pending connections.
- HTTP client pool metrics.
- Cache hits/misses/evictions when providers are instrumented.
- Custom business metrics such as reservation successes/failures.

OpenTelemetry adds distributed traces showing whether time goes into controllers, repositories, remote clients, or messaging consumers.

Never enable unbounded-cardinality metric labels such as user ID, order ID, or raw URLs. Use endpoint templates, tenant tiers, or bounded tags.

### 7.3. Managed service metrics

| Service type | Metrics to track |
| --- | --- |
| Relational database | CPU, memory, connections, query latency, IOPS, disk queue, locks, deadlocks, replica lag |
| NoSQL | Request latency, consumed capacity/RUs, throttled requests, hot partitions/keys, retries |
| Cache | Hits/misses, evictions, memory, connection count, command latency, replication lag |
| Messaging | Publish/consume rates, queue depth, oldest message age, unacked messages, redeliveries, DLQ |
| Object storage | Request counts, latency, throughput, errors/throttles, egress |
| Compute | Instance count, startup latency, CPU, memory, concurrency, pending requests, scale events |

Never look at CPU in isolation. Low database CPU paired with high pending pool waits points to pool sizing or lock contention. Rising queue backlogs with low consumer CPU point to consumer concurrency caps or I/O dependencies.

### 7.4. AWS: CloudWatch

For Amazon RDS, CloudWatch provides metrics such as `CPUUtilization`, `DatabaseConnections`, `FreeableMemory`, `FreeStorageSpace`, `ReadLatency`, `WriteLatency`, `ReadIOPS`, `WriteIOPS`, `DiskQueueDepth`, and `ReplicaLag` (depending on engine/topology).

For ElastiCache, monitor engine CPU, memory, evictions, connections, cache hits/misses, and replication lag per engine. For SQS, track queue depth and age of oldest message; for Lambda/ECS/EKS, monitor concurrency, throttles, task/instance counts, and resource utilization.

CloudWatch collects RDS metrics at a default one-minute interval; enable Enhanced Monitoring, Performance Insights, or tracing/logs when deeper granularity is needed. [Amazon RDS CloudWatch metrics](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-metrics.html) and [CloudWatch monitoring overview](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/monitoring-cloudwatch.html).

### 7.5. Azure: Azure Monitor and Azure Load Testing

Azure Load Testing integrates with Azure Monitor to collect server-side resource metrics for app components configured in the test. Its dashboard lets you compare:
- Client response time, throughput, and error rate.
- Server-side metrics for App Service, Azure SQL, Cosmos DB, and supported resources.
- Load generator engine health including CPU, memory, network, and virtual users.

If load generator engines saturate CPU/memory/network, results reflect generator limits rather than application limits. [Azure Load Testing server-side metrics](https://learn.microsoft.com/en-us/azure/app-testing/load-testing/how-to-monitor-server-side-metrics) and [test run results dashboard](https://learn.microsoft.com/en-us/azure/app-testing/load-testing/how-to-understand-test-run-results-dashboard).

For Azure SQL, Cosmos DB, and Azure Managed Redis, track service-specific metrics like CPU/workers, data I/O, RU consumption/throttling, cache memory/latency, and connections.

### 7.6. Google Cloud: Cloud Monitoring

For Cloud Run, monitor request count and latency, container CPU/memory utilization, instance count and max concurrent requests, container startup latency, billable instance time, pending latency, and user execution latency where metric breakdowns exist.

For Cloud SQL, monitor CPU, memory, active connections, storage, read/write operations, Query Insights, and replication lag if replicas exist. For Pub/Sub, Cloud Storage, and Memorystore, track backlog/oldest unacked message, request latency, throughput, cache memory/hits, and connections per service.

Cloud Run provides built-in metrics in Cloud Monitoring; Cloud SQL exposes CPU, connection, storage, and I/O metrics. [Cloud Run monitoring](https://docs.cloud.google.com/run/docs/monitoring), [Cloud SQL monitoring](https://docs.cloud.google.com/sql/docs/mysql/monitor-instance).

### 7.7. Correlating via timestamps and test run IDs

Every system must share a synchronized time window and carry a test run ID:
- Load generator records run ID and scenario.
- Spring Boot logs/traces record run ID or trace context.
- Database query comments/labels where safe and supported.
- Message attributes carrying run ID.
- Monitoring dashboards annotated with ramp-up, hold, and ramp-down markers.
- Recorded deployment revision and configuration revision.

Without correlation, a metric spike might originate from an unrelated workload or scheduled background job.

## 8. Bottleneck analysis

### 8.1. Reading signals before changing configuration

| Symptom | Likely cause | Verification step |
| --- | --- | --- |
| Rising p95, high app CPU | CPU-bound serialization or business logic | Profile JVM, thread dumps, CPU flame graphs |
| Rising p95, low app CPU, high pool pending | Connection pool exhaustion or slow dependency | Inspect active/idle/pending counts, query latency |
| High database CPU/IO | Queries/indexes/schemas or undersized tier | Query Insights, slow queries, execution plans |
| Database connections hitting limit | Per-instance pool too large or rapid instance scale-out | Sum total connections, check max connections |
| Low cache hit ratio | Unstable keys, overly short TTL, or data pattern | Analyze hits/misses by cache name |
| High cache memory/evictions | Large working set or unbounded entries | Check key cardinality, value sizes, TTLs |
| Growing queue backlog | Slow consumers, small batches, blocked downstream | Measure processing rate, oldest message age, retries |
| Rising throttling | Quota/RU/capacity limits | Check service quotas and request patterns |
| Rising pending latency during spikes | Cold starts or insufficient instances | Check startup latency, min/max instances |
| Rising dropped iterations | Too few VUs or saturated load generator | Check generator CPU/memory/network |
| Latency varies by region | Network path or cross-region calls | Compare DNS/connect/TLS and regions |
| Errors climb after retries | Retry storm or non-idempotent operations | Inspect retry policies and idempotency keys |

### 8.2. Connection pools and instance counts

With Spring Boot using HikariCP, total connections scale with application instance count:

\[
C_{total} = N_{instances} \times P_{max} + C_{background}
\]

Where `N_instances` is maximum concurrent application instances, `P_max` is `maximumPoolSize` per instance, and `C_background` covers connections from workers, migrations, admin tools, monitoring, or other services.

For example, 12 instances with max pool 20 each plus 40 background connections can demand 280 connections. If the database permits fewer than that, scaling out causes connection rejections.

Never raise `maximumPoolSize` merely because requests are waiting. If the database is already saturated, a larger pool makes contention worse. Measure query latency, active connections, pending pool waits, and database capacity together.

### 8.3. Autoscaling and concurrency

For managed compute:
- Overly high concurrency lets each instance hold too many concurrent requests and connections.
- Overly low concurrency spawns too many instances and connections.
- Low min instances increases cold starts.
- Low max instances causes pending queues or throttling.
- Startup duration and readiness probes govern when instances start taking traffic.

Test one parameter at a time under identical workloads. Check both instance-time cost and database connections after every scaling change.

### 8.4. Queue and consumer throughput

If an API only publishes a message and responds immediately, API latency can look low even while consumers fall behind. Measure end-to-end latency from publish through processing completion.

Consumers can be bottlenecked by worker/partition count, batch size, ack deadline or visibility timeout, database write rate, external API rate limits, retries/DLQs, ordering keys, or hot partitions.

Never raise consumer concurrency without confirming downstream databases/caches can absorb the higher write rate.

## 9. Evidence-based production configuration tuning

### 9.1. A repeatable tuning loop

~~~mermaid
flowchart TD
    SLO["Define SLO and workload"] --> BASE["Run baseline on real managed services"]
    BASE --> OBS["Correlate client, app and provider metrics"]
    OBS --> BOT["Identify the first bottleneck"]
    BOT --> HYP["Form one configuration hypothesis"]
    HYP --> CHANGE["Change one variable in staging"]
    CHANGE --> TEST["Repeat the same test"]
    TEST --> COMPARE["Compare latency, errors, capacity and cost"]
    COMPARE --> PASS{"SLO and cost improved?"}
    PASS -->|Yes| CANARY["Canary / gradual production rollout"]
    PASS -->|No| ROLLBACK["Revert and test another hypothesis"]
    CANARY --> MON["Monitor and keep rollback ready"]
~~~

### 9.2. Changing one variable at a time

Suppose you want to raise throughput:
1. Capture baseline with current instance size and concurrency.
2. Raise CPU or memory while holding concurrency fixed.
3. Re-run the exact same test.
4. Restore the baseline.
5. Change concurrency while holding CPU/memory fixed.
6. Re-run and compare.
7. Check database connections, cost, and tail latency as well.

If you change CPU, pool size, cache TTL, and database tier all at once, you cannot tell which change produced the gain or regression.

### 9.3. Commonly tuned configuration groups

| Component | Parameters to test | Risks to check |
| --- | --- | --- |
| Spring Boot runtime | CPU/memory, thread pools, max concurrency | GC, queueing, instance cost |
| Autoscaling | Min/max instances, target utilization, scale delay | Cold starts, scale bursts, quotas |
| HikariCP | `maximumPoolSize`, `connectionTimeout`, `idleTimeout` | Database connection limits |
| Database | Machine tier, storage/IOPS, indexes, query plans | Cost, locks, replication |
| Cache | TTL, max memory, eviction, pool size | Stale data, cache stampedes |
| Messaging | Consumer count, batch size, prefetch, ack | Backlogs, duplicates, downstream overload |
| HTTP client | Connection pool, timeouts, keep-alive | Pending acquires, socket exhaustion |
| Retries | Max attempts, backoff, jitter | Retry storms, duplicate writes |
| Object storage | Multipart threshold, concurrency, buffer size | Memory, request cost, egress |

Never relax security settings or disable TLS to inflate benchmark scores. Performance must be measured under the exact security posture intended for production.

### 9.4. Tuning by bottleneck

- **CPU-bound:** profile code, cut serialization overhead, optimize algorithms, then consider raising CPU or instances.
- **Database-bound:** tune queries/indexes, eliminate N+1, batch, reduce locks; upgrade tiers only after verification.
- **Pool-bound:** sum total connections, inspect leaks/pending waits, align pools with database capacity.
- **Network-bound:** verify regions, private endpoints, TLS reuse, payloads, and cross-region traffic.
- **Cache-bound:** inspect hit ratios, key design, TTLs, stampedes, and evictions.
- **Queue-bound:** measure processing rates, scale consumers within limits, tune batching and downstream.
- **Cold-start-bound:** trim startup work, pre-warm, or adjust min instances if cost permits.
- **Quota-bound:** verify real quotas, cut requests, batch, or request quota increases well ahead of production events.

### 9.5. Weighing cost alongside performance

A change is only an improvement if it does not trade away reliability or push cost beyond acceptable bounds.

Track cost per 1,000 successful requests, cost per processed message, cost per GB or object operation, database tier and storage/IOPS costs, cache memory-hours, egress and cross-region traffic, observability ingestion/retention, and load generator costs.

For example, enlarging a cache may cut database reads while raising memory cost. Raising min instances may cut cold starts while raising billable instance hours. Compare unit economics, not just total spend over one short test run.

## 10. Quotas, costs, and stop conditions

### 10.1. Quota vs. capacity

A quota is a provider-enforced cap on a project/account/region/service. Capacity is the processing capability of provisioned resources. A workload can hit a quota before CPU or memory runs high.

Track:
- API request quotas.
- Concurrent request/instance quotas.
- Database connection limits.
- NoSQL read/write capacity or RU/s.
- Message publish/receive quotas.
- Storage request rates.
- Load testing engine capacity.
- Regional resource quotas.

When throttling appears, do not simply crank up retries. Inspect quotas, partition hot spots, burst limits, and service tiers.

### 10.2. Budgets and stop conditions

Define stop conditions upfront, such as:
- Error rate exceeding threshold over a sustained window.
- p99 breaching safety thresholds.
- Database connections reaching protective caps.
- Queue backlogs exceeding limits.
- Rapidly climbing service throttling.
- Generator CPU/network saturation.
- Projected spend exceeding the test budget.
- Any impact on tenants or workloads outside the test.

Operators must be able to stop the generator and roll back config immediately. Never wait for a scheduled test timer to finish once a stop condition trips.

### 10.3. Do not treat production as an ad-hoc stress lab

Production load testing is only appropriate with dedicated planning and strict controls:
- Scheduled test window and clear owner.
- Bounded traffic, canarying, or rate-limited traffic replay.
- No customer-impacting mutations or real transactions.
- Kill switch and tested rollback.
- Notification to operations and dependency owners.
- Active monitoring of SLOs and error budgets.
- Never deliberately probe hard breaking limits or failovers outside approved windows.

Normally, stress/spike/soak tests belong in production-like staging. Production can use canaries, synthetic monitoring, or tightly bounded controlled experiments to confirm real-world behavior.

## 11. Step-by-step performance testing workflow

### Step 1 — Lock down the question

For example: “Can the browse API sustain 100 RPS with p95 under 500 ms and error rate under 1% when running on Cloud Run and Cloud SQL staging?”

A crisp question dictates the workload, metrics, and duration.

### Step 2 — Prepare the environment

- Deploy the exact artifact/version under test.
- Configure real managed dependencies.
- Load production-like test data.
- Verify regions, networking, and IAM.
- Configure quotas, budget alerts, and stop conditions.
- Enable metrics, logs, and tracing.

### Step 3 — Smoke test

Send a few requests. Verify responses, test data, cleanup, and monitoring.

### Step 4 — Baseline

Run a small repeatable workload and save results. Record p50/p95/p99, RPS, error rate, resource utilization, and cost.

### Step 5 — Load/stress/spike/soak

Pick the load profile matching your question. Ramp in stages and hold long enough for resource scaling to stabilize.

### Step 6 — Pinpoint the bottleneck

Correlate client metrics with application traces and provider metrics. Identify the first component to saturate or introduce latency.

### Step 7 — Form a hypothesis and change one setting

Adjust one parameter or tightly coupled group. Record the configuration revision.

### Step 8 — Re-run under identical conditions

Keep workload, test data, region, generator, and duration identical to baseline. If anything differs, document the difference explicitly.

### Step 9 — Compare and decide

Compare SLOs, capacity, errors, cost, and headroom. Accept a change only when results repeat reliably without degrading reliability.

### Step 10 — Canary and monitor production

Roll out gradually, watch live metrics, and keep rollback ready. Never treat a single staging benchmark as an absolute guarantee for every production traffic pattern.

## 12. Reporting test results

A report detailed enough for another team to reproduce should capture:

| Field | Contents |
| --- | --- |
| Test run ID | Unique identifier |
| Application version | Git SHA / image digest |
| Configuration revision | Config hash or version |
| Infrastructure | Region, service tier, instance size, network |
| Dependency versions | Engine/version, cache tier, queue config |
| Data profile | Row counts, object sizes, distribution, seed |
| Load generator | Tool/version, location, instance count |
| Workload | Scenarios, RPS/VUs, think time, duration |
| Test type | Smoke/load/stress/spike/soak |
| Client results | Throughput, p50/p95/p99, errors |
| App results | CPU, memory, GC, threads, pools |
| Dependency results | CPU, connections, latency, throttles, backlogs |
| Cost | Usage/cost estimate, egress, generator |
| Findings | Bottleneck, evidence, root cause |
| Change tested | Single configuration changed |
| Decision | Accept/reject/retest |
| Limitations | Production differences, quotas, or missing metrics |

### 12.1. Before-and-after comparison

Sample comparison table (illustrative figures):

| Metric | Baseline | Candidate | Notes |
| --- | ---: | ---: | --- |
| Throughput | 80 RPS | 100 RPS | +25% |
| p95 | 620 ms | 430 ms | Improved |
| p99 | 1,800 ms | 1,050 ms | Tail latency reduced |
| Error rate | 0.8% | 0.4% | Improved |
| DB CPU | 88% | 82% | Still needs headroom |
| DB connections | 170 | 185 | Check limits |
| Cost/1,000 requests | 1.00 unit | 1.12 units | +12% |

Never declare the candidate better solely because p95 dropped. Verify that p99, error rate, resource headroom, and cost all stay within target bounds.

## 13. Common load testing pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Tests pass yet production is slow | Staging differs in tier, data volume, or network | Document differences, mirror topology |
| Results vary on every run | Unfixed workload/data seed or background jobs | Lock test data, time windows, and dependencies |
| RPS stalls despite adding VUs | Arrival rate unconfigured or generator saturated | Check executor, max VUs, and generator health |
| High dropped iterations | Insufficient VUs or SUT too slow | Inspect generator and iteration duration |
| Good average yet very high p99 | Tail latency from locks, queues, GC, or network | Analyze percentiles, traces, and outliers |
| Low app CPU yet requests wait | Pool, connection, or dependency bottleneck | Check pending pools, connections, and remote spans |
| High database CPU | Table scans/locks/indexes or undersized tier | Query Insights, execution plans |
| Connection refused | Total pools exceed max connections or failover | Compute connection budget and check DB limits |
| Unrealistically great cache tests | Pre-warmed cache or overly repetitive keys | Test cold/warm separately with realistic key distributions |
| Queue backlog grows after test | Consumer throughput below publish rate | Measure oldest message age and processing rate |
| Rising throttling | Quota/capacity/partition limits | Check quotas, capacity, and request distribution |
| Surprise cloud bill spike | Autoscaling, egress, or long test duration | Budget alerts, resource caps, and stop conditions |
| Non-repeatable results | Multiple parameters changed at once | Change one variable, repeat test |
| Metrics cannot explain latency | Sampling granularity too coarse | Use finer logs/traces and correlation IDs |
| Test generator is the bottleneck | Exhausted CPU, memory, network, or file descriptors | Scale generator or reduce protocol overhead |

## 14. Hands-on exercises

### Exercise A — Building a workload model

From a Spring Boot API, pick three user journeys. Specify request mix, think time, payload sizes, peak RPS, and p95/p99 SLOs.

### Exercise B — Provisioning staging with managed services

Provision a dedicated project/subscription and deploy Spring Boot with managed database, cache, and messaging. Compare region, network, tier, and IAM against production; document differences.

### Exercise C — Smoke and baseline with k6

Write a k6 script with checks and thresholds. Run a smoke test, then a low-load baseline. Save JSON results and the test run ID.

### Exercise D — Load and stress tests

Use `ramping-arrival-rate` to ramp traffic gradually. Find the highest RPS where p95, p99, and error rate still satisfy SLOs.

### Exercise E — Autoscaling spike test

Generate a sudden traffic surge. Measure startup latency, pending requests, instance count, database connections, and queue backlog. Inspect cold starts and scale-out behavior.

### Exercise F — Soak test

Hold load at 60–70% of expected peak long enough to meet test goals. Monitor heap, GC, connections, cache memory, and queue age.

### Exercise G — Testing database pools

Test two distinct HikariCP configurations while holding everything else constant. Calculate maximum total connections across instances and compare against database limits.

### Exercise H — Cloud-specific metric observation

Run the same workload while watching AWS CloudWatch/RDS metrics, Azure Load Testing/Azure Monitor, and Google Cloud Monitoring/Cloud Run/Cloud SQL metrics. Identify which metrics explain the bottleneck.

### Exercise I — Single-variable optimization

Pick a proven bottleneck. Change one setting, re-run the identical test, and compare p95/p99, throughput, errors, resource headroom, and cost.

### Exercise J — Reporting and rollout

Produce a report following the template. Propose production settings, canary rollout, alerts, and rollback triggers. Explain any remaining staging/production differences.

### Self-check questions

1. Why cannot mocks and emulators replace performance tests against real managed services?
2. Which differences between staging and production can skew results?
3. What information does a workload model need?
4. How does a closed workload differ from an open workload?
5. What does Little's Law help estimate?
6. Why must SLOs be defined before running tests?
7. How does a smoke test differ from a baseline test?
8. Which questions do stress, spike, and soak tests answer?
9. Why must a single endpoint never represent all traffic?
10. What does k6's `arrival-rate` executor control?
11. What do dropped iterations indicate?
12. How do `check()` assertions differ from `thresholds`?
13. Why must you monitor load generator health?
14. Which metrics should be collected from Spring Boot?
15. Which RDS bottlenecks can CloudWatch help uncover?
16. Which service does Azure Load Testing integrate with for server-side metrics?
17. How does Cloud Run pending latency differ from user execution latency?
18. Why can low CPU coincide with high latency?
19. How do you calculate total connections when an application autoscales?
20. Why does enlarging a connection pool not always raise throughput?
21. What do queue backlog and oldest message age reveal?
22. Why must you check quotas before stress testing?
23. How do you define stop conditions and budget alerts?
24. Why should you change only one configuration variable at a time?
25. What details must a performance test report capture?
26. When is production testing acceptable and what guardrails are required?
27. Why should you compare cost per successful request?
28. Why does passing in staging not guarantee production will always meet SLOs?

**Expected outcome:** learners can build a workload model, run smoke/load/stress/spike/soak tests against real managed services in a safe environment, collect client/application/provider metrics, pinpoint bottlenecks with evidence, test controlled configuration changes, and propose production rollouts grounded in SLOs, quotas, reliability, and cost.

## References

- [Google Cloud — Conduct load testing](https://docs.cloud.google.com/support/docs/peak-events/conduct-load-testing)
- [Cloud Run — Load testing best practices](https://docs.cloud.google.com/run/docs/about-load-testing)
- [Cloud Run — Monitor health and performance](https://docs.cloud.google.com/run/docs/monitoring)
- [Cloud SQL — Monitor instances](https://docs.cloud.google.com/sql/docs/mysql/monitor-instance)
- [AWS — Monitoring Amazon RDS metrics with CloudWatch](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/monitoring-cloudwatch.html)
- [AWS — Amazon RDS metrics reference](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-metrics.html)
- [Azure Load Testing — Monitor server-side metrics](https://learn.microsoft.com/en-us/azure/app-testing/load-testing/how-to-monitor-server-side-metrics)
- [Azure Load Testing — Understand test run results](https://learn.microsoft.com/en-us/azure/app-testing/load-testing/how-to-understand-test-run-results-dashboard)
- [Grafana k6 — Scenarios](https://grafana.com/docs/k6/latest/using-k6/scenarios/)
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/)
- [Grafana k6 — Test for performance](https://grafana.com/docs/k6/latest/examples/get-started-with-k6/test-for-performance/)
- [Grafana k6 — Automated performance testing](https://grafana.com/docs/k6/latest/testing-guides/automated-performance-testing/)

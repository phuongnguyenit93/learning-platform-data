# Diagnosing Cloud Run Timeouts, Cold Starts, and Out-of-Memory Errors

A Java/Spring service on Cloud Run can behave normally during off-peak hours, yet when traffic rises, experience HTTP 504s, spiking p99 response times, or instance restarts. After a deployment, the first request to a new revision may also be much slower than subsequent requests. Logs might record only a request timeout, while the true cause is slow JVM startup, an exhausted database connection pool, or the container exceeding its memory limit.

These three incident classes produce similar symptoms yet demand different investigations:

- **Timeouts:** a request fails to complete within a deadline at some layer; you must find where time is spent and distinguish client, Cloud Run, application, and dependency timeouts.
- **Cold starts:** Cloud Run must provision a new instance, pull the image, and initialize the container/application before serving requests; you must reduce startup latency or maintain warm capacity.
- **Out of memory (OOM):** a process or container exceeds its memory budget, causing JVM errors, container termination, restarts, and failed requests.

In the **CLOUD_PROVIDERS_GCP** module, this lesson connects Cloud Run with Java/Spring, IAM, VPC, Cloud SQL, autoscaling, Cloud Monitoring, and SRE practices. The goal is to build a diagnostic workflow anchored in metrics, request logs, system logs, and traces, and then tune timeouts, concurrency, CPU, memory, or startup policies based on evidence.

After this lesson, you will be able to:

- Distinguish HTTP 504s caused by Cloud Run request timeouts from timeouts inside the application or dependencies.
- Read request logs, container logs, system logs, and key Cloud Run metrics.
- Identify cold start drivers across images, the JVM, Spring context, dependency initialization, and networking.
- Use minimum instances, startup CPU boost, startup probes, and concurrency appropriately.
- Diagnose memory pressure, JVM heap OOMs, and container memory limit exceeded errors.
- Size JVM heap below the container memory limit while accounting for native/direct memory, thread stacks, caches, and temporary files.
- Design safe timeout budgets, retries, idempotency, and background processing.
- Build an incident runbook and validate improvements using SLOs and cost metrics.

## 1. Classify Symptoms Before Changing Configuration

Do not bump timeout, memory, and CPU all at once the moment you see a 504. First, classify the symptoms:

| Observed Symptom | Cause Category to Investigate |
|---|---|
| HTTP 504 after a fairly consistent duration | Cloud Run request timeout, proxy/client deadline, or dependency timeout |
| First request after idle/deploy is slow; subsequent requests are fast | Cold start, JVM/Spring initialization, image pull, or connection warm-up |
| Instance restarts; system log reports memory limit exceeded | Container exceeded its memory limit |
| Java logs show \`java.lang.OutOfMemoryError\`, yet Cloud Run has not killed the instance | Application-level JVM heap/native memory pressure |
| High CPU, rising p95, normal memory | CPU-bound code, serialization, queries, or excessive concurrency |
| Low CPU, requests still stall | Pool exhaustion, database/network waits, lock contention, or downstream timeouts |
| Only one revision fails after deploy | Image, environment, JVM flags, traffic split, or new config differences |
| Failures happen only during peak traffic | Max instances, concurrency, connection pools, quotas, or dependency capacity |

### Three First Questions

1. **Did the request reach the container?** If not, inspect ingress, scaling, startup, and request logs.
2. **Did the container start processing and logging?** If yes, locate the last span or log line before the timeout.
3. **Is the instance still alive after the error?** If it restarted, check system logs, memory, and startup probes; if still alive, check whether the request kept running after the client received the error.

An HTTP 504 only indicates that the request did not finish within the active deadline. It does not prove the database is slow, the JVM is out of memory, or Cloud Run had a platform outage.

## 2. Cloud Run Has Multiple Timeout Layers

A request traverses several layers:

~~~mermaid
flowchart LR
    C[Client / mobile / browser] --> G[Gateway / load balancer]
    G --> R[Cloud Run request timeout]
    R --> A[Spring request handler]
    A --> P[Connection pool]
    P --> D[Cloud SQL / API / cache]
~~~

Each layer can enforce its own deadline:

| Layer | Example | Investigation Question |
|---|---|---|
| Client | HTTP client timeout, mobile network | Did the client close the connection before the server? |
| Gateway | API Gateway, external load balancer | Is the gateway timeout shorter than Cloud Run's? |
| Cloud Run | Revision request timeout | Did the request exceed the configured timeout? |
| Application | Spring MVC/WebFlux, servlet container | Are threads blocked, deadlocked, or queued? |
| Database/client | Hikari checkout, JDBC query timeout | Waiting on connections, queries, or locks? |
| External API | Payment, shipping, identity | Do downstreams have nested retries or timeouts? |

### Cloud Run Default Timeout and Limits

Cloud Run services default to a **300-second (5-minute)** request timeout and allow up to **3,600 seconds (60 minutes)**. When exceeded, Cloud Run closes the connection and returns HTTP 504. The container instance **is not automatically terminated** simply because a request timed out; application code may keep executing the remaining work. That can leave instances consuming CPU, connections, and memory even after the client already received 504.

Therefore, increasing the timeout is only appropriate when the workload legitimately needs more time and handles recovery safely. If a handler keeps writing data after the client times out, client retries can create duplicate mutations. Use idempotency keys, durable job states, or status checks before re-executing work.

### Setting Timeout with gcloud

~~~bash
gcloud run services update orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --timeout=45s
~~~

Each service config update creates a new revision. The command above illustrates changing the timeout; before applying in production, confirm the new timeout fits inside gateway/client deadlines and is not masking a hung dependency.

Inspect the active configuration:

~~~bash
gcloud run services describe orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format=yaml
~~~

### Building an Outside-In Timeout Budget

Suppose an API has a 5-second budget:

| Component | Illustrative Deadline |
|---|---:|
| Cloud Run request | 5,000 ms |
| Application handler | 4,500 ms |
| External API | 1,500 ms |
| JDBC query | 1,000 ms |
| Connection pool checkout | 300 ms |

Budgets may run sequentially or in parallel; never mechanically sum concurrent branches. Each dependency must finish well inside the overall deadline so the application has time to handle errors and emit a response. Never set pool or SQL timeouts longer than the overall request deadline.

For Java HTTP clients, pass explicit deadlines or timeouts instead of relying on overly generous library defaults. When using retries, the total time across all attempts and backoffs must fit inside the request budget.

## 3. Timeout Does Not Mean the Request Was Cancelled

Cloud Run returns 504 when a request times out, yet the container may continue processing. Consider this sequence:

1. Client sends \`POST /orders\`.
2. Server writes the order and calls payment.
3. Request times out before the server returns a response.
4. Client sees 504 and retries the request.
5. Server processes it a second time because the first attempt is still running.

If the endpoint is not idempotent, the system can create two orders or charge twice.

### Mandatory Controls for Write Operations

- Accept a stable idempotency key from the client or derive one deterministically from the business request.
- Persist processing state and results by key in the database.
- Use transactions/unique constraints to prevent concurrent requests from duplicating side effects.
- On client retry, return the stored result or `IN_PROGRESS` status.
- Enforce dependency timeouts and abort work when insufficient deadline remains.
- For long-running work, offload to a job/queue and return HTTP 202 with an operation ID.

### When to Move to Asynchronous Processing?

If processing routinely exceeds request deadlines, avoid stretching the request timeout to maximum just to hold connections open. Instead:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Cloud Run API
    participant Q as Pub/Sub / Cloud Tasks
    participant W as Worker / Cloud Run Job
    participant D as Database
    C->>R: POST /exports
    R->>D: Create PENDING operation
    R->>Q: Enqueue operation_id
    R-->>C: 202 Accepted + operation_id
    Q->>W: Execute job
    W->>D: Update RUNNING / SUCCEEDED / FAILED
    C->>R: GET /operations/{id}
    R->>D: Read status
    R-->>C: 200 + operation status
~~~

Cloud Tasks suits scheduled HTTP invocations, controlled retries, and rate throttling; Pub/Sub suits event publishing and fan-out; Cloud Run Jobs suit batch tasks that run to completion. Choose based on semantics, not just request duration.

## 4. Reading Cloud Run Request, Container, and System Logs

Cloud Run emits three log streams:

- **Request logs:** HTTP request details, latency, status, revision, and request attributes.
- **Container logs:** logs written by the application to stdout/stderr or supported logging agents.
- **System logs:** platform events such as container startup, shutdown, health checks, and instance errors.

When investigating 504s or OOMs, inspect all three streams. Reading only application logs misses why Cloud Run terminated a container.

### Viewing Logs with gcloud

~~~bash
gcloud run services logs read orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --limit=100
~~~

Or query Cloud Logging:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
timestamp >= "2026-11-19T00:00:00Z"
~~~

To filter errors:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
severity>=ERROR
~~~

In Logs Explorer, filter by revision, trace ID, request ID, and time range. Use UTC timestamps when correlating logs across Cloud Run, databases, and external systems.

### Structured Logging

Applications should emit JSON with structured fields:

~~~json
{
  "severity": "WARNING",
  "message": "downstream request exceeded budget",
  "service": "orders-api",
  "revision": "orders-api-00042-abc",
  "request_id": "req-8c3e",
  "trace_id": "TRACE_ID",
  "route": "POST /orders",
  "dependency": "inventory",
  "duration_ms": 1400,
  "remaining_deadline_ms": 500
}
~~~

This is an example log schema. Never log access tokens, session cookies, passwords, payment payloads, PII, or secrets. When attaching traces, use Cloud Trace–compatible formats and stable correlation IDs.

## 5. Key Cloud Run Metrics to Monitor

Cloud Monitoring exposes metrics for Cloud Run services and revisions. Essential metrics:

| Metric / Group | How to Use It |
|---|---|
| Request count | Traffic breakdown by status, revision, and service |
| Request latencies | p50/p95/p99 to identify tail latency |
| Container startup latency | Time required to initialize a new instance |
| Container CPU utilization | CPU usage relative to allocation |
| Container memory utilization | Memory pressure per instance/container |
| Container instance count | Active instances, showing scale-out/scale-in |
| Maximum concurrent requests | Observed concurrency per instance |
| Billable container instance time | Understand billed instance runtime |
| Container CPU/memory allocation | Compare allocated resources against usage |

Exact metric names can vary by resource type and configuration; select metrics in Cloud Monitoring Metrics Explorer under resource type \`Cloud Run Revision (cloud_run_revision)\` or \`Cloud Run Instance (cloud_run_instance)\`.

### Combined Diagnostic Charts

Over the same time range, plot:

1. Request latency p95/p99.
2. Request count and 5xx/504 counts.
3. Container startup latency.
4. Instance count and maximum concurrent requests.
5. CPU utilization.
6. Memory utilization.
7. Database connection pool active/pending counts and query latency.

If p99 spikes alongside memory nearing 100% and instance restarts, suspect memory pressure. If p99 rises with concurrency and CPU near allocation, inspect CPU and concurrency. If startup latency rises alongside cold start counts, inspect image size, initialization, and min instances.

### Separating Service Averages from Hot-Spot Instances

Service-wide averages can hide a single hot instance. If one instance receives huge payloads or builds an oversized cache, revision-wide average memory may still look moderate. Whenever possible, drill down by instance/revision and correlate request and container logs at the exact timestamp.

## 6. Diagnosing Cold Starts

Cold starts happen when Cloud Run creates a new instance to serve traffic or a new revision. Startup latency can consist of:

- Instance provisioning and pulling image layers.
- Starting the container and JVM.
- Class loading, dependency injection, and Spring application context initialization.
- Initializing connection pools, DNS, TLS, and client libraries.
- Synchronous config/secret fetches, cache warming, or model loading.
- Startup probes and sidecar initialization if present.

### Measure Cold Starts Instead of Guessing

Plot container startup latency and request latency together. Compare:

- The first request after scaling from zero.
- The first request after deploying a new revision.
- Subsequent requests on a warm instance.
- Requests hitting newly scaled-out instances during peak traffic.

If startup latency is high while post-startup request times are low, focus on optimizing boot time. If startup is fast yet every request is slow, it is not a cold start—inspect queries, networking, CPU, and concurrency.

### Common Root Causes

| Cause | Symptom | Remediation |
|---|---|---|
| Large container image | Slow startup whenever a new instance spins up | Multi-stage builds, slim images, strip unused files |
| Heavy Spring context | Long initialization logs, heavy bean scanning | Narrow component scans, selective lazy init, trim beans |
| JIT / class loading | First post-startup request is slow | Warm-up endpoints or appropriate AOT/compilation |
| DB connection initialization | New instances wait on DB or pool setup | Smaller initial pool, lazy connections, cap concurrency |
| Synchronous secret/config fetch | Startup blocks on external services | Cache valid config, bounded timeouts, controlled fallbacks |
| DNS/TLS handshakes | First dependency call is slow | Reuse HTTP clients, connection pooling, keep-alive |
| VPC egress/networking | Slow only when calling private dependencies | Check Direct VPC egress/connector, routes, and DNS |
| Sidecars | Instance waits for auxiliary containers | Trim startup work, check startup probes and ordering |

## 7. Reducing Cold Starts via Cloud Run Configuration

### Minimum Instances

By default, Cloud Run can scale to zero when idle. Setting minimum instances keeps warm capacity ready to reduce the odds of requests waiting on startup:

~~~bash
gcloud run services update orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --min=1
~~~

Minimum instances incur charges even while idle per the applicable billing mode. This is a **best-effort floor**, not a guarantee an instance stays alive forever; instances can still restart or be affected by quotas, capacity, or application crashes. High availability still requires multiple instances, multi-region/architectural resilience, and clear SLOs.

### Startup CPU Boost

Startup CPU boost temporarily grants extra CPU during startup and for 10 seconds after the instance begins. Enable it with:

~~~bash
gcloud run services update orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --cpu-boost
~~~

This feature can cut startup time when initialization is CPU-bound, but **does not** fix timed-out dependencies, unreachable databases, or memory leaks. Extra CPU during boost can affect billing; measure before and after enabling.

### Optimizing Images and Spring Boot Startup

- Use lean base images containing only runtime dependencies.
- Pin dependencies and structure Docker layers for effective caching.
- Avoid loading large models or datasets synchronously at startup if they can safely lazy-load.
- Never run heavy schema migrations on every instance startup.
- Reuse HTTP clients, SDK clients, and connection pools instead of recreating them per request.
- Narrow component scanning and disable unnecessary auto-configurations.
- Audit the classpath and startup logs; enable Spring startup metrics in appropriate environments.
- Adopt CDS/AOT or native images only when benchmarks show runtime gains outweigh build cost and compatibility risks.

Do not use lazy initialization to defer failures until the first user request; mandatory dependencies should be validated before taking traffic.

## 8. Startup Probes and Liveness Probes

Cloud Run supports container startup and liveness probes. Startup probes determine when the application has booted; liveness probes detect when a running process becomes unhealthy. The startup probe must succeed before the liveness probe begins checking.

Example service YAML configuration:

~~~yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: orders-api
spec:
  template:
    spec:
      containers:
      - image: REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:VERSION
        ports:
        - containerPort: 8080
        startupProbe:
          httpGet:
            path: /startupz
            port: 8080
          periodSeconds: 2
          timeoutSeconds: 1
          failureThreshold: 15
        livenessProbe:
          httpGet:
            path: /livez
            port: 8080
          periodSeconds: 10
          timeoutSeconds: 2
          failureThreshold: 3
~~~

This manifest is illustrative; substitute your actual image and project. \`/startupz\` should succeed only once the application is ready to accept requests. \`/livez\` should check process liveness—never chain external dependencies in a way that restarts every instance simultaneously if a database blips.

### Liveness Is Not Readiness

Cloud Run services support startup and liveness probes per the platform contract; do not copy a Kubernetes readiness probe blindly into Cloud Run assuming identical GKE semantics. Internally, the app may still expose a readiness health group, but always verify how Cloud Run actually routes traffic.

Overly strict probes trigger restart loops; overly lenient probes keep hung instances alive. Set timeouts and failure thresholds from measured startup times and failure modes. Never use liveness probes as a substitute for dependency monitoring.

## 9. Diagnosing Out-of-Memory: Container Limits vs. JVM Heap

Cloud Run terminates an instance when memory exceeds its allocated limit. Memory must cover the executable, application heap and non-heap regions, native memory, thread stacks, buffers, any sidecars, and files written to the filesystem.

In Java, **heap is not total container memory**. A JVM process also consumes:

- Metaspace and class metadata.
- JIT code cache.
- Direct byte buffers / NIO.
- Thread stacks.
- Native libraries, TLS/HTTP clients, and compression buffers.
- Memory mappings and agents/profilers.
- In-app caches, object allocations, and other runtime regions.

If a container has a 1 GiB limit and you set \`-Xmx1g\`, Cloud Run may kill the JVM before the heap ever reaches `Xmx`. Always leave headroom based on empirical profiling.

### Distinguishing Two Types of OOM

**JVM heap OOM:** application logs may show \`java.lang.OutOfMemoryError: Java heap space\`, \`GC overhead limit exceeded\`, or direct buffer errors. The container can stay alive if the process does not exit and total memory remains under the container limit; requests may hang or fail.

**Container memory limit exceeded:** total memory breaches the container cap; Cloud Run terminates the instance. System logs show instance termination, in-flight requests fail, and a fresh instance spins up.

Do not rely solely on exit code 137 to conclude OOM; `SIGKILL` can have other causes. Cross-check system logs, memory utilization, JVM logs, and restart timestamps.

## 10. Sizing Memory for Java/Spring

A budgeting model:

\[
M_{container} \ge M_{heap} + M_{metaspace} + M_{direct} +
M_{threads} + M_{native} + M_{filesystem} + M_{headroom}
\]

These components are not strictly independent and vary at runtime. Treat the formula as a checklist, not an exact equation.

Example for a 1 GiB container limit:

| Component | Illustrative Budget |
|---|---:|
| Java heap | 600 MiB |
| Metaspace/code cache | 100 MiB |
| Direct buffers/native | 80 MiB |
| Thread stacks | 60 MiB |
| Temp files / off-heap cache | 40 MiB |
| Headroom | 144 MiB |
| **Total** | **1,024 MiB** |

This is an illustrative breakdown; always measure a real memory profile. Workloads with many threads, heavy direct buffers, or large JSON payloads can require significantly more non-heap memory.

### Bounding Heap with JVM Flags

Example setting max heap as a percentage of container memory:

~~~dockerfile
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0 -XX:+ExitOnOutOfMemoryError"
~~~

Modern JVMs are container-aware; however, the ideal percentage depends on JDK version, container limit, native libraries, thread count, and workload. \`60%\` is an **illustrative** figure, not a universal rule. \`ExitOnOutOfMemoryError\` forces the process to exit on OOM so the platform replaces the instance, though it can fail in-flight requests; pair it with idempotency, health checks, and a clear recovery strategy.

You can set \`-Xmx\` explicitly for tight control, but never set it equal to the full container limit. With multi-container/sidecar services, verify each container's individual memory allocation in Cloud Run config.

### The Filesystem Also Consumes Memory

Cloud Run's writable container filesystem is generally backed by memory; writing large files drives up container memory consumption. Never write uploads, large reports, large caches, or heap dumps into \`/tmp\` without budgeting for them. Use Cloud Storage for durable files and stream payloads rather than buffering everything in heap.

## 11. Finding Memory Leaks and Allocation Spikes

An OOM may come from a transient load spike or a slow leak over time. Distinguish the patterns:

| Metric Pattern | Hypothesis |
|---|---|
| Memory climbs steadily over hours and never drops after GC | Object leak, unbounded cache, or retained references |
| Memory rises with concurrent requests and drops afterward | Large working set/buffers, high concurrency |
| Heap is flat while container memory grows | Native/direct memory, threads, mmap, or filesystem writes |
| OOM only on large payloads | Buffering full request/file bodies, giant JSON object graphs |
| High memory after a recent deploy | New dependency, cache, classloader, or agent |
| High memory when DB slows down | Requests hold objects/connections/threads longer; queues pile up |

### JVM Observability Tools

- Java Flight Recorder (JFR) to analyze allocations, GC pauses, threads, and locks.
- Java heap usage/GC metrics via securely configured Micrometer or JMX exporters.
- Thread dumps when suspecting blocked thread pools.
- Heap dumps in staging or under a secure handling procedure when analyzing object retention.
- Native Memory Tracking (NMT) when diagnosing native allocations and its overhead is acceptable.

Heap dumps can contain sensitive user data and grow huge. Never enable automatic heap dumps to Cloud Run's in-memory filesystem without careful assessment; store dumps in secure locations with strict retention and access controls.

### Common Java/Spring Culprits

- Caches backed by `Map` without eviction or TTL.
- Buffering entire HTTP response bodies in memory.
- Oversized JDBC result sets or missing pagination.
- Unbounded thread pool queues.
- Async tasks retaining request/context objects too long.
- Logging full large payloads.
- Direct `ByteBuffer` or Netty pools not releasing as expected.
- Creating new SDK clients or connection pools per request.
- Hibernate persistence contexts retaining too many entities in batch jobs.

Fixes typically involve streaming, pagination, bounded queues, cache eviction policies, proper resource closing, and right-sized batches.

## 12. How Concurrency, CPU, and Memory Interact

Cloud Run can route multiple concurrent requests to a single instance. Raising concurrency reduces instance counts, yet shares CPU, memory, and connection pools across more simultaneous requests. If each request builds a large object graph, peak memory scales nearly linearly with concurrency.

### Concurrency Configuration Example

~~~bash
gcloud run services update orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --concurrency=20 \
  --max=30
~~~

This illustrates capping concurrent requests per instance at 20 and maximum instances at 30 using current `gcloud` flags. Run \`gcloud run services update --help\` if your CLI version uses different flag names. Capping max instances can queue requests when hitting the ceiling; evaluate queuing and downstream capacity carefully.

### How to Tune Concurrency

1. Start from your current baseline and representative traffic.
2. Measure CPU, memory, request latency, and database pool pending counts.
3. Lower concurrency if per-instance memory/CPU spikes or tail latency degrades.
4. Raise concurrency when requests are mostly I/O-bound and memory headroom remains healthy.
5. Multiply max instances × concurrency to estimate peak load on databases and external APIs.
6. Test bursts, cold starts, and scale-out in staging.

Lower concurrency can increase instance counts, cold starts, and cost; higher concurrency can increase memory pressure and latency. There is no single optimal number for every service.

## 13. CPU Allocation and Background Tasks

Cloud Run offers different CPU/billing allocation modes. With request-based CPU allocation, CPU is primarily allocated while an instance processes requests; never rely on background threads running after a response is sent for critical work. For durable background execution, use Pub/Sub, Cloud Tasks, Cloud Run Jobs, or instance-based billing as appropriate.

CPU-bound requests suffer when CPU allocation is too low; I/O-bound requests may see little benefit from extra vCPUs. Measure CPU utilization and thread profiles before scaling CPU.

### Startup CPU Boost Is Not Continuous CPU Boost

Startup CPU boost only assists initialization and a brief window after instance start. It does not grant extra CPU for steady-state requests. If p99 stays high after startup, inspect steady-state CPU allocation, concurrency, queries, and dependencies.

## 14. Networking and Dependencies Can Also Cause Cold Starts or Timeouts

A service that boots fast yet cannot connect to Cloud SQL or Secret Manager still looks like a cold start. Check:

- Are Cloud Run and the database in compatible regions?
- Are Direct VPC egress or Serverless VPC Access connectors configured with valid subnets, routes, and firewalls?
- DNS resolution, NAT, private IPs, and connection establishment.
- Is the Cloud SQL connector/Auth Proxy initialized once and reused?
- Do connection pools open too many connections during scale-out?
- Are external APIs throttling or experiencing slow TLS handshakes?
- Are retries amplifying load on an already overloaded dependency?

Never create database connections per request. Initialize clients and pools once per instance, reuse them, and handle stale connections, pool timeouts, and graceful shutdown cleanly.

## 15. Java/Spring: Illustrative Timeout and Pool Configuration

HikariCP configuration example:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://DB_HOST:5432/orders
    username: orders_app
    hikari:
      maximum-pool-size: 8
      minimum-idle: 1
      connection-timeout: 500
      validation-timeout: 1000
      max-lifetime: 1800000
      pool-name: orders-db-pool
  mvc:
    async:
      request-timeout: 4000
~~~

Millisecond values here must be tuned to your driver, database, and request deadline. Hikari's \`connection-timeout\` bounds waiting for a connection from the pool; it is neither the SQL execution timeout nor the Cloud Run request timeout.

### Total Connection Budget

If a service scales up to 30 instances and each holds a pool of up to 8 connections, theoretical connections from this service alone reach:

\[
30 \times 8 = 240\ connections
\]

Add other services, migrations, monitoring, admin sessions, and failover overhead. A database can be overwhelmed even though each individual instance keeps a modest pool.

### Timeouts When Calling Dependencies

Java HTTP client example:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofMillis(500))
    .build();

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create(inventoryUrl))
    .timeout(Duration.ofSeconds(2))
    .GET()
    .build();

HttpResponse<String> response = client.send(
    request, HttpResponse.BodyHandlers.ofString());
~~~

This snippet requires importing \`java.net.http.*\` and \`java.time.Duration\`. Instantiate and reuse the client at bean/service scope instead of recreating it per request. For async/reactive code, apply proper timeout operators and cancellation semantics.

### Do Not Retry Every Error

- Retry 429/503 or transient network errors only for idempotent operations with remaining deadline.
- Never blindly retry 400/401/403/404/422.
- For mutating POSTs, enforce idempotency keys and state checks.
- Use exponential backoff with jitter and bounded attempt counts.
- Avoid stacking uncoordinated retries across client, application, service mesh, and downstream SDKs without a shared retry budget.

## 16. HTTP 504 Investigation Workflow

~~~mermaid
flowchart TD
    A[Received 504] --> B{Cloud Run request log exists?}
    B -->|No| C[Check client, gateway, ingress, and DNS]
    B -->|Yes| D{Did container log request start?}
    D -->|No| E[Check cold start, scaling, startup, and capacity]
    D -->|Yes| F[Inspect trace/spans and last log]
    F --> G{Waiting on dependency?}
    G -->|Yes| H[Check pool, SQL, network, and downstream timeout]
    G -->|No| I[Check CPU, locks, threads, and payload handling]
    E --> J{Memory near limit or instance restart?}
    H --> K[Set appropriate deadlines/retries/idempotency]
    I --> K
    J -->|Yes| L[Analyze OOM and memory]
    J -->|No| M[Check image, JVM, and probes]
    L --> K
    M --> K
    C --> K
~~~

### First-10-Minutes Investigation Checklist

1. Record request ID, trace ID, UTC timestamp, revision, and route.
2. Verify whether the 504 came from Cloud Run's request timeout or from a gateway/client.
3. Compare request latency against the configured timeout.
4. Check instance count, startup latency, and concurrency.
5. Inspect CPU/memory utilization, container restarts, and system logs.
6. Find the slowest span: database, external API, DNS, connection pool, or application code.
7. Check recent deployments/revisions, traffic splits, and configuration changes.
8. For mutating requests, confirm idempotency before manually retrying anything.

## 17. Cold Start Investigation Workflow

1. Filter the first request of a new revision or after an idle window.
2. Compare container startup latency against post-startup request processing time.
3. Read system and container logs to see when the process begins listening on the port.
4. Check image size, layer download time, and startup dependencies.
5. Analyze Spring startup logs, bean initialization, and JVM warm-up.
6. Measure database, secret, and network connection initialization times.
7. Test minimum instances or startup CPU boost on a test revision.
8. Compare p95/p99 latency, billable instance time, and cost before/after.

Never crank up min instances indefinitely just to mask a bloated startup sequence. If only one endpoint demands ultra-low latency, consider splitting out a smaller service or using targeted warm-up.

## 18. OOM Investigation Workflow

1. Check system logs for memory limit exceeded or instance termination events.
2. Search container logs for \`OutOfMemoryError\`, GC overhead, or direct buffer errors.
3. Correlate memory utilization over time with request count and concurrency.
4. Verify the container memory limit and JVM max heap flags on the failing revision.
5. Check file writes, request/response buffering, caches, thread pools, and batch sizes.
6. For heap OOMs, capture a heap/JFR profile in a securely controlled environment.
7. For rising native memory, inspect direct buffers, threads, JNI, and agents.
8. Lower concurrency or cap payload sizes to reduce peak pressure while hunting root cause.
9. Raise memory limits only after measuring actual usage and cost impact.
10. Roll out the new revision and monitor memory slope, OOM rate, p99 latency, and instance restarts.

### Inspecting Deployed Memory Limits

~~~bash
gcloud run services describe orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml(spec.template.spec.containers)"
~~~

Verify \`resources.limits.memory\`, CPU, and any sidecars. Inspect the live traffic-serving revision rather than trusting YAML files in Git that may not match what is deployed.

## 19. Active Incident Mitigation Runbook

### Rising Timeouts Without OOM

- Temporarily throttle traffic or lower concurrency if databases/dependencies are overloaded.
- Disable heavy non-essential features or offload batches/reports to queues.
- Cap retries so they do not amplify load.
- Increase request timeouts only when work genuinely needs more time and is idempotent.
- If a new revision caused the regression, roll traffic back to the last stable revision.

### Cold Starts After Deployment

- Inspect revision startup health and logs.
- Keep an appropriate minimum instance count if latency SLOs demand it.
- Enable startup CPU boost if startup is CPU-bound.
- Trim image/initialization overhead and avoid long synchronous startup dependency chains.
- Monitor idle instance costs and post-deploy request latency.

### OOM / Restart Loops

- Lower concurrency or temporarily cap max instances to avoid overwhelming the database.
- If a new revision introduced a memory leak, roll back the revision.
- Bump memory temporarily only after checking config and quotas, and record it explicitly as a temporary mitigation.
- Ensure JVM max heap does not equal the container memory limit.
- Never write huge heap dumps to the in-memory filesystem when containers are already near the limit.
- Plan leak/buffer fixes and benchmark before reopening full traffic.

## 20. SLOs, Alerting, and Preventing Recurrence

Suggested SLIs:

| SLI | How to Measure | Example Target |
|---|---|---|
| Request success rate | Eligible requests not returning 5xx/timeout | 99.9% over a 28-day window |
| p95/p99 latency | Request latency by route | p95 under 500 ms for read APIs |
| Cold start latency | Container startup latency | p95 below product-defined threshold |
| Memory headroom | `1 - memory utilization` | Maintain adequate headroom at peak |
| OOM/restart rate | Instance terminations due to memory | Zero OOMs under projected load |
| Pool wait | Hikari pending/checkout time | p95 well below request budget |
| Dependency latency | Downstream spans | Every dependency within its budget |

Example targets are illustrative only; tailor them to your product and error budget. Never alert solely on average CPU or average memory; use p95/p99, per-instance max views, and error rates to catch hot instances.

### Essential Alerts

- 5xx/504 rate spikes above baseline over a short window.
- p95/p99 latency breaching SLO.
- Rising container startup latency or revisions failing to scale.
- Sustained high memory utilization approaching limits.
- Instance restarts or OOM events.
- Concurrency hitting ceilings or max instances saturating.
- Rising Hikari pending connections indicating DB pool exhaustion.
- Rising dependency timeout/error rates.

Pair every alert with a runbook and an owner/on-call rotation. Alerts without actionable steps create operational noise.

## 21. Hands-On Labs: Diagnosing Three Incidents

### Lab A: Dependency-Induced Timeout

**Scenario:** \`POST /orders\` returns 504 right around the request timeout. Application logs show processing started with no completion log; traces show the inventory call span dragging on.

**Execution:**

1. Record the request ID and locate the request log.
2. Inspect the trace to measure connection wait time and inventory call duration.
3. Check client timeout, Cloud Run timeout, and dependency deadline.
4. Test a shorter downstream timeout so the app returns a controlled error before the Cloud Run deadline.
5. Send the same idempotency key twice and confirm no duplicate reservation is created.

**Expected outcome:** identify the slow layer and ensure a clean response/error path before Cloud Run times out.

### Lab B: Java/Spring Cold Starts

**Scenario:** the first request after 10 minutes of zero traffic takes 3 seconds, while subsequent requests take 150 ms.

**Execution:**

1. Compare container startup latency against request latency.
2. Inspect Spring startup logs and database client/pool initialization times.
3. Enable startup CPU boost on a test revision.
4. Set minimum instances = 1 for a measured test window.
5. Compare p95/p99 latency and billable instance time cost.

**Expected outcome:** quantify how much each option reduces cold starts and how much idle capacity costs.

### Lab C: Memory Pressure

**Scenario:** a large JSON upload API shows memory utilization climbing with concurrency and occasional instance restarts.

**Execution:**

1. Inspect system logs and memory utilization by revision.
2. Inspect JVM \`-Xmx\`, direct memory, thread counts, and temporary files.
3. Lower concurrency from 80 to 20 on a test revision.
4. Switch payload handling from full buffering to streaming.
5. Measure peak memory, throughput, p99 latency, and instance counts.

**Expected outcome:** cut peak memory while preserving throughput/SLOs without excessive cost growth.

## 22. Quick Troubleshooting Matrix

| Symptom | Likely Cause | Action |
|---|---|---|
| 504 at a consistent recurring duration | Cloud Run request timeout or client deadline | Inspect timeouts at all layers and traces |
| 504 yet instance continues processing | Cloud Run closes connection; handler is not killed | Enforce idempotency, deadline cancellation, and async jobs |
| 504 right after deploy | Cold start or dependency initialization | Check startup latency, image, Spring logs, and probes |
| First request slow, subsequent ones fast | Cold start / JIT / cache / connection warm-up | Min instances, CPU boost, controlled warm-up |
| Container killed; system log shows memory limit | Container OOM | Budget memory, lower concurrency/buffers, or raise memory |
| JVM heap OOM without restart | App-level `OutOfMemoryError` below container limit | Capture JFR/heap profile, handle OOM, review liveness |
| Low CPU, high pool wait | Exhausted connection pool or long-held connections | Inspect Hikari active/pending and transaction duration |
| High CPU, high latency | CPU-bound code or excessive concurrency | Profile code, lower concurrency, or raise CPU after measuring |
| Min instances do not eliminate all cold starts | Instance restarts, capacity/quotas, or deploys | Check startup logs, quotas, and best-effort behavior |
| Startup probe keeps failing | Wrong endpoint or slow initialization | Check port/path/deadline; do not loosen indefinitely |
| Still OOM after raising memory | Leak, direct/native memory, or file buffering | Profile non-heap, filesystem usage, and thread pools |
| Raising timeout increases costs | Handlers keep running after client timeouts | Propagate deadlines, cancel work, offload to queues/jobs |

## 23. Pre-Closure Incident Checklist

- [ ] Determined whether the timeout originated at client, gateway, Cloud Run, application, or dependency.
- [ ] Inspected request, container, and system logs alongside traces.
- [ ] Correlated request latency, startup latency, CPU, memory, concurrency, and instance counts.
- [ ] Verified active revision timeouts and every dependency timeout.
- [ ] Enforced idempotency on write operations during client retries or request timeouts.
- [ ] Offloaded long-running tasks to queues/jobs with durable operation status.
- [ ] Analyzed cold starts across image, JVM/Spring, networking, and initialization.
- [ ] Measured both effectiveness and cost of min instances / CPU boost.
- [ ] Verified startup/liveness probes cannot trigger restart loops.
- [ ] Ensured JVM heap leaves headroom for native memory, direct buffers, threads, and filesystem.
- [ ] Distinguished JVM heap OOM from container memory limit exceeded.
- [ ] Verified concurrency and max instances fit database/dependency capacity.
- [ ] Executed safe rollback/mitigation and monitored SLOs post-change.
- [ ] Assigned action items, owners, dashboards, alerts, and runbooks to prevent recurrence.

## 24. Conclusion

Cloud Run timeouts, cold starts, and out-of-memory errors often look alike as slow requests or 5xx errors, yet have distinct root causes. Timeouts demand end-to-end deadline analysis and safe handling of unknown outcomes; cold starts demand measuring container startup latency and optimizing images, JVM, and dependency initialization; OOMs demand distinguishing heap from total container memory while checking native memory, concurrency, and temporary files.

The most effective workflow is **identify the revision and request → read logs/traces → correlate metrics → isolate the bottleneck layer → test one controlled change → re-measure SLOs and cost**. Only increase timeouts, CPU, or memory when telemetry proves it is the actual bottleneck. For Java/Spring applications, connection pooling, thread/concurrency limits, JVM heap sizing, and retry behavior must be designed hand-in-hand with Cloud Run settings so the service scales reliably.

## References

- [Cloud Run troubleshooting](https://docs.cloud.google.com/run/docs/troubleshooting)
- [Configure request timeout for services](https://docs.cloud.google.com/run/docs/configuring/request-timeout)
- [Monitor health and performance](https://docs.cloud.google.com/run/docs/monitoring)
- [Cloud Run logging](https://docs.cloud.google.com/run/docs/logging)
- [Configure memory limits for services](https://docs.cloud.google.com/run/docs/configuring/services/memory-limits)
- [Configure CPU limits and startup CPU boost](https://docs.cloud.google.com/run/docs/configuring/services/cpu)
- [Set minimum instances for services](https://docs.cloud.google.com/run/docs/configuring/min-instances)
- [Container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
- [General development tips for Cloud Run](https://docs.cloud.google.com/run/docs/tips/general)
- [Cloud Run quotas and limits](https://docs.cloud.google.com/run/quotas)
- [Cloud Monitoring overview](https://docs.cloud.google.com/monitoring/docs)
- [Spring Boot Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Java Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api.html)

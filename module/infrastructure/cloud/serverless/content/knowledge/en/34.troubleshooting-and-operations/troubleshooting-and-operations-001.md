# Investigating Slow APIs Caused by Cold Start and Downstream Latency

An API running on a serverless platform can respond slowly due to two major groups of causes: the Java execution environment needs initialization time before handling a request (*cold start*), or the function has to wait on backend systems such as a database, HTTP service, cache, or queue (*downstream latency*). Both causes can occur at the same time, yet their remedies differ. Increasing memory or keeping functions warm will not fix a slow database query; optimizing queries will not eliminate JVM initialization time either.

This lesson explains how to measure end-to-end latency, classify slow requests, read logs and traces, add measurements in Java, inspect downstream dependencies, and choose appropriate latency reduction measures. The operational goal is to keep the API within its SLO limits at a reasonable cost while ensuring retries, scaling, and error handling remain safe.

After this lesson, you will be able to:

- Break down the response time of a serverless request into measurable stages.
- Distinguish cold starts from downstream latency using per-request and percentile data.
- Use structured logs, metrics, and distributed traces to pinpoint the stage consuming time.
- Measure processing time in Java with a monotonic clock and set timeouts for dependency calls.
- Choose ways to optimize cold starts, HTTP connections, connection pools, data queries, and retries.
- Evaluate the impact of concurrency, idempotency, cost, and SLOs before changing the architecture.

## 1. Break Down Latency Before Fixing Issues

The latency seen by a client is the total time across multiple layers. A practical model for a serverless API is:

\[
T_{client} = T_{edge} + T_{queue} + T_{init} + T_{handler} + T_{downstream} + T_{response}
\]

Where:

| Component | Meaning | Example signals to measure |
|---|---|---|
| `T_edge` | Time at DNS, CDN, load balancer, or API gateway | Gateway latency, integration latency, TLS handshake |
| `T_queue` | Time a request waits for resource allocation or a worker | Queue age, event age, concurrency wait time |
| `T_init` | Time to create the environment and initialize the runtime/function | Init duration, cold-start marker, class loading |
| `T_handler` | Time running logic inside the function | Validation, mapping, serialization, CPU, and GC |
| `T_downstream` | Time waiting on services called by the function | Pool wait, DNS, connect, TLS, query, remote processing |
| `T_response` | Time packaging and transmitting the response to the client | Payload size, serialization, gateway egress |

This is a model to guide measurement, not always a direct sum of spans. If a function calls three services in parallel, the slowest branch usually determines the wait time; if the calls run sequentially, their durations add up. Traces will show parent-child relationships and parallel work.

Do not collapse everything into a single `Duration` number. For example, a function running for 900 ms might spend 40 ms on Java processing, 30 ms waiting to acquire a connection, and 830 ms waiting on the database. Looking only at duration makes it easy for the operations team to optimize the JVM by mistake when the query is the actual bottleneck.

### 1.1. Read Percentiles Instead of Only Looking at Averages

- **p50** describes the typical request: half of requests complete within this duration or faster.
- **p95** shows the experience of requests that are slower than most users experience.
- **p99** exposes slow tails caused by cold starts, pool exhaustion, retries, GC, or overloaded downstream systems.
- **SLO breach rate** indicates how many requests exceed the committed threshold, for example over 800 ms.

Averages can look healthy even when a small group of requests is very slow. Therefore, compare p50, p95, p99, and error rate across the same route, region, function version, request size, and time window. Do not compare the p99 of a group with very few requests against the p99 of a high-traffic group without checking sample size.

For example, a p50 at 120 ms while p99 reaches 2.5 seconds often suggests an issue affecting only a subset of requests: newly initialized environments, exhausted connection pools, re-established DNS/TLS, or certain data queries with poor execution plans. When both p50 and p95 rise together, it usually indicates widespread load or downstream slowdown.

### 1.2. What Is a Cold Start?

In the FaaS model, the platform creates an execution environment to run a function. The first invocation in a new environment may need to perform tasks such as:

1. Allocating the execution environment and preparing the runtime.
2. Starting the JVM and loading the required libraries.
3. Loading classes, running static initializers, and creating the dependency injection container or framework context.
4. Reading configuration and initializing serializers, HTTP clients, SDKs, connection pools, or shared components.
5. Only then running the handler for the first request.

Subsequent invocations can reuse the same environment and skip most of the initialization cost. However, the platform reserves the right to create or reclaim environments based on load and internal policies. You must not assume a subsequent request will always run on the same instance, nor use static variables to store business state across requests.

Java can incur significant initialization overhead when an application pulls in many dependencies, framework classpath scanning, reflection, complex logging configurations, or static initializers that perform I/O. Client and pool initialization can also occur during the init phase or be pushed onto the first request, depending on when classes are loaded.

### 1.3. What Is Downstream Latency?

A downstream system is any system a function must call to complete a request: a REST/gRPC service, database, cache, object storage, message broker, identity provider, or third-party API. The time of a call typically consists of several parts:

- Waiting to acquire a connection from a pool or semaphore.
- DNS lookup and TCP connection establishment.
- Performing TLS handshake and authentication.
- Waiting for the backend service to schedule processing.
- Executing a query, transaction, or remote logic.
- Transferring and reading the response, and decoding the payload.
- Waiting between retry attempts if transient errors occur.

A slow downstream system can cause a function to occupy concurrency longer. When many invocations wait on the database simultaneously, the rising number of execution environments can open even more connections, overloading the database and slowing requests further. This is a common amplification loop in serverless systems.

## 2. Distinguish Cold Start from Downstream Latency

Group requests before drawing conclusions. A single slow request is not enough to prove a cold start or a database failure.

| Observation | Likely cause | How to verify |
|---|---|---|
| First request of a new environment is slow; subsequent requests are fast | Cold start or lazy initialization | Correlate platform init duration with first-invocation markers and traces |
| Warm requests are still slow; database/HTTP spans dominate total time | Downstream latency | Inspect query duration, remote spans, pool wait, and connection time |
| p99 rises as load increases, accompanied by throttling or rising queue age | Insufficient concurrency, downstream limits, or queue backlog | Compare concurrency, throttles, queue age, connection count, and error rate |
| Function duration is low, but client/gateway latency is high | Edge, gateway, network, or queue | Compare client timing, gateway timing, and function timing |
| Only certain requests show multiple repeated calls | Retries or transient errors | Record attempt count, retry reason, and total time consumed |
| Slow after an idle period | Expired connections, DNS/TLS, or new environment | Measure pool wait, connect/TLS, connection resets, and init duration |
| p50 is good but p99 is bad, with no init duration | Tail latency in downstream, GC, locks, or pools | Use traces and per-stage metrics; do not assume it is a cold start |

A reliable cold-start signal must correlate a request with a new environment or the init metric provided by the platform. A static variable marking the first invocation is only a process-level diagnostic signal; it does not replace official platform metrics. Conversely, if slow requests have long database spans even when the environment is warm, optimizing cold starts will not resolve that root cause.

### 2.1. Define the Scope of Impact

Before digging deeper, clearly document:

- Route, method, region, stage, and function version/alias.
- Time window of the incident, traffic level, request count, and recent deployments.
- p50/p95/p99, SLO breach rate, timeouts, 4xx/5xx, and retries.
- Any special request sizes, payload types, or business branches.
- Whether the incident affects all regions or just one, all downstream systems or a single dependency.

If only one route is slow, start from the dependencies and processing branches specific to that route. If multiple routes slow down together and call the same database, cache, or identity provider, prioritize checking the shared dependency.

## 3. Data Needed for Investigation

An effective investigation workflow combines three signal types: metrics for trends, logs for specific events, and traces for timing relationships across components.

### 3.1. Metrics at Each Layer

| Layer | Metrics to track | Question to answer |
|---|---|---|
| Client/API gateway | Request count, p50/p95/p99, integration latency, 4xx/5xx, timeout | Is the client waiting on the gateway or the function? |
| FaaS platform | Invocation, duration, init duration, error, throttle, concurrency, queue/event age | Are there new environments, concurrency limits, or backlogs? |
| JVM/function | Init time, CPU, heap, GC pause, memory used, serialization time | Is the function computing, doing GC, or waiting on I/O? |
| HTTP client | Pool wait, DNS/connect/TLS, response time, timeout, status, retry count | Is the connection or the remote service slow? |
| Database | Connection count, pool pending, query latency, lock wait, CPU, I/O, transaction time | Is the pool exhausted or is the query/DB overloaded? |
| Cache/broker | Hit ratio, command latency, queue depth, oldest message age, redelivery | Are cache misses or backlogs increasing latency? |

Metric names differ across AWS Lambda, Azure Functions, Google Cloud Functions/Cloud Run Functions, and other platforms. Use the equivalent metrics provided by your provider. In AWS Lambda, the `REPORT` log line can include `Init Duration` on cold starts; metrics such as `Duration`, `Errors`, `Throttles`, and `ConcurrentExecutions` help put duration in the context of load. Do not assume a metric unavailable in your provider exists simply because of the naming used in this example.

Track metrics as histograms or distributions to compute percentiles. Averaging pre-aggregated averages cannot accurately replace request p95/p99. Tag metrics with low-cardinality dimensions such as route, region, function version, and downstream service. Do not use user IDs, request IDs, or URLs with query strings as metric dimensions because they create too many time series and can expose sensitive data.

### 3.2. Structured Logs

Each invocation should have a record or group of records correlatable via `request_id` and `trace_id`. Useful fields include:

- `request_id`, `trace_id`, `route`, `method`, `region`, `function_version`.
- `cold_start_candidate`, `init_duration_ms` if provided by the platform.
- `total_ms`, `validation_ms`, `business_ms`, `serialization_ms`.
- `downstream_service`, `downstream_ms`, `pool_wait_ms`, `attempt`, `status_code`.
- `outcome`, `error_type`, `timeout_stage`, and `concurrency` if available.

Do not log access tokens, cookies, secrets, full payloads, or personal data just to investigate latency. If you need to identify a request type, use a normalized route template or business operation type. Do not log URLs containing sensitive query strings.

Logs must distinguish total duration from individual downstream durations. A log saying `request completed in 2400 ms` does not show where those 2.3 seconds went. A log with `total_ms=2400`, `db_ms=1900`, `http_ms=120`, `handler_ms=300` narrows the scope substantially.

### 3.3. Distributed Traces

Traces describe the path of a request through the gateway, function, and called services. Every remote call should have its own span, such as `inventory.lookup`, `orders.query`, or `payment.authorize`. Use OpenTelemetry or the provider's tracing capability to propagate trace context across HTTP headers and message metadata.

When reading a trace:

1. Find the root span corresponding to the API request.
2. Identify which child span lies on the critical path and consumes the most time.
3. Separate pool/connection wait time from actual processing time if the library supports it.
4. Check whether parallel spans are blocking on each other.
5. Correlate attempts and exceptions to detect hidden retries inside SDKs.

Not every trace captures the initialization phase before the handler runs. Combine traces with platform init duration and logs. Sampling can also miss slow requests if using pure random sampling; consider tail-based sampling to retain traces with high latency or errors while controlling cost and sensitive data.

## 4. Step-by-Step Investigation Workflow

### Step 1: Lock In Symptoms and Target Thresholds

Select a specific route and time window. Record p50, p95, p99, SLO breach rate, error rate, and traffic volume. Compare against a normal period, the same time of day, or the same load level. Confirm whether the incident started after a deploy, configuration change, traffic spike, or downstream change.

Do not start by increasing memory, timeout, or concurrency. These changes can mask symptoms, increase cost, or put heavier load on downstream systems without identifying the root cause.

### Step 2: Compare Timing Across Client, Gateway, and Function

- If the client sees slowness but the gateway does not, check DNS, client connectivity, CDN, or user-side networking.
- If gateway integration latency is high and function duration is also high, investigate inside the function.
- If the gateway is slow while function duration is low, inspect the gateway, queue, network connection, serialization, or wait time before the function starts.
- If the function times out while the downstream is still processing, check deadlines and remote call cancellation.

Make sure numbers use the same units and refer to the same requests. Do not subtract two independent percentiles to infer a stage's duration; use traces or request-level data to calculate differences.

### Step 3: Split Requests into Cold and Warm Groups

Correlate init duration, first-invocation markers, and environment creation timestamps if provided by the platform. Compare the latency distribution of the group with init against the group without init. If only the cold group breaches the SLO, measure initialization and the first request's handler separately. If the warm group is still slow, shift focus to the handler and downstream calls.

Self-recorded markers in Java must be understood accurately: a static variable lives only within one runtime environment, resets when a new environment is created, and does not measure the full platform allocation time. Use it for initial grouping; use provider logs/metrics to confirm.

### Step 4: Find the Downstream Dominating the Critical Path

For warm requests, open slow traces and sort spans by duration. Check:

- Is connection pool wait time increasing?
- Do DNS, TCP, or TLS appear on every request or only after idle periods?
- Is the database waiting on locks, scanning many rows, or running N+1 queries?
- Is an HTTP service returning 429/5xx, queueing internally, or sending large responses?
- Is an SDK retrying automatically without appearing in application logs?
- Can calls run in parallel instead of unnecessarily sequentially?

Cross-check traces with downstream metrics. If the function records a call taking 1.8 seconds and the database also records the query taking 1.8 seconds, the evidence is fairly clear. If the function waits 1.8 seconds while the server only processes for 80 ms, the difference may lie in pools, networking, proxies, or queues.

### Step 5: Form a Testable Hypothesis

A good hypothesis states a cause, expected signals, and an experiment. For example: "p99 rises because the database pool has only two connections per environment; when concurrency increases, invocations wait on the pool for over 500 ms." The prediction is that `pool_wait_ms` rises along with `pending` while query execution time stays relatively stable. Test by carefully increasing the pool limit or using an appropriate proxy, then monitor connection count and p99.

Avoid changing multiple variables at once. If you change memory, pool size, timeout, and retries together, either good or bad outcomes become hard to explain.

### Step 6: Test and Verify

Run tests in an environment whose network, database, and concurrency limits resemble production. Test both cold and warm paths, steady load, and bursts. Compare the same request types and payload sizes before and after changes. Monitor latency, error rate, throttling, downstream saturation, and cost throughout the test.

A single successful call after deployment does not prove cold starts are gone: the request might happen to land on an already warm environment. You need to observe enough invocations and new environments to evaluate properly.

## 5. Measuring Time in Java

### 5.1. Use a Monotonic Clock

Measure elapsed intervals with `System.nanoTime()`. Do not use `System.currentTimeMillis()` to compute elapsed time because the wall clock can be adjusted. Convert to milliseconds only when logging or emitting metrics.

The following example illustrates recording the first request in a runtime environment and separately timing a repository call. Types such as `ApiRequest`, `ApiResponse`, `InvocationContext`, `repository`, and `logger` represent application components; replace them with your project's actual types.

```java
import java.util.concurrent.atomic.AtomicBoolean;

public final class ApiHandler {
    private static final AtomicBoolean FIRST_INVOCATION =
            new AtomicBoolean(true);

    private final OrderRepository repository;
    private final Logger logger;

    public ApiHandler(OrderRepository repository, Logger logger) {
        this.repository = repository;
        this.logger = logger;
    }

    public ApiResponse handle(ApiRequest request, InvocationContext context) {
        long requestStarted = System.nanoTime();
        boolean firstInvocation = FIRST_INVOCATION.compareAndSet(true, false);
        long repositoryMs = -1;
        String outcome = "success";

        try {
            long repositoryStarted = System.nanoTime();
            Order order = repository.findById(request.orderId());
            repositoryMs = elapsedMillis(repositoryStarted);

            return ApiResponse.from(order);
        } catch (RuntimeException exception) {
            outcome = "error";
            throw exception;
        } finally {
            long totalMs = elapsedMillis(requestStarted);
            logger.info(
                    "request_id={} first_invocation_candidate={} "
                            + "repository_ms={} total_ms={} outcome={}",
                    context.requestId(), firstInvocation,
                    repositoryMs, totalMs, outcome);
        }
    }

    private static long elapsedMillis(long startedAtNanos) {
        return (System.nanoTime() - startedAtNanos) / 1_000_000;
    }
}
```

`FIRST_INVOCATION` is only a process-level marker. It flags the first handler call observed by this class in the current environment; it does not measure runtime allocation time and does not replace the provider's `Init Duration`. If the class is loaded lazily, initialization occurring before class loading is also excluded from this marker.

In a real application, create spans for each stage and record durations even when calls fail or time out. Do not log `repository_ms` only on success: if an exception occurs before assigning the variable, include a status field like `repository_outcome=timeout` to distinguish "not called" from "called but failed".

### 5.2. Measure and Bound HTTP Calls

Java applications should reuse a thread-safe HTTP client within the scope of a runtime environment instead of creating a new client per request. For example, with `java.net.http.HttpClient` (Java 11 and later):

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class CatalogClient {
    private static final HttpClient HTTP = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(250))
            .version(HttpClient.Version.HTTP_2)
            .build();

    public String getItem(URI uri) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofMillis(900))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response = HTTP.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new DownstreamException(
                    "Catalog returned HTTP " + response.statusCode());
        }
        return response.body();
    }
}
```

`connectTimeout` bounds connection establishment; `HttpRequest.timeout` bounds the request duration. Both must be chosen according to the remaining invocation deadline. The 250 ms and 900 ms values above are illustrative only, not default settings for every system.

Reusing the client leverages keep-alive connections and reduces repeated socket/TLS creation. However, connections can be closed by the server or proxy while idle. Handle stale connection errors and let the client reconnect in a controlled manner. Do not store responses or user-specific data in static fields just because the client is shared.

For other HTTP clients or SDKs, explicitly verify timeouts for each phase: connection acquisition, connect, TLS, response/read, and overall request. A timeout that applies only to connect does not limit response wait time. Set finite timeouts on every remote call.

### 5.3. Measure Connection Pools and Database Queries

If using a JDBC pool, separate at least three metrics: time waiting to acquire a connection, query execution time, and time holding a connection in a transaction. High pool wait can appear even when queries are fast. High query duration can stem from missing indexes, scanning many rows, lock contention, or an overloaded database.

Do not set a large pool size by guesswork. In serverless, many environments can exist concurrently. If function concurrency is 80 and each environment has a max pool of 10 connections, the system can theoretically create up to roughly 800 connections. Actual numbers depend on environment count, threads, and how the pool opens connections, but this multiplication shows why a small per-instance pool can still put heavy pressure on a database.

For databases with connection limits, consider a managed proxy/pooler, limiting function concurrency, reducing per-environment pool size, shortening transactions, and opening connections only when needed. Configure idle timeout and validation to align with the database/proxy's connection closing policy. Do not hold a transaction open while calling an unrelated HTTP service.

## 6. Reduce Cold Starts for Java Functions

Only optimize cold starts after measuring the cold invocation ratio and how much init time contributes to SLO breaches. If cold starts represent a tiny fraction of traffic and p99 is mainly driven by the database, investing in startup speed may yield little improvement.

### 6.1. Reduce Work During Initialization

- Remove unused dependencies, duplicate libraries, and unnecessary framework modules.
- Limit classpath scanning, reflection, and building large containers if the function only uses a few components.
- Avoid network API calls, database queries, or remote configuration fetches in static initializers when unnecessary.
- Create shared serializers, clients, and configuration once per environment when they are safe to reuse.
- Measure class loading, dependency injection, configuration, and client creation separately to see where time actually goes.
- Keep artifacts lean and inspect the dependency tree and JAR/container image packaging.

Lazy initialization can shift cost from init to the first request. This helps when a component is rarely used, but it slows down the first request hitting that branch. Measure both init duration and first-request latency, not just one of them.

### 6.2. Choose Runtime and Startup Techniques

Depending on the platform, consider:

- **Increasing allocated memory/CPU:** some platforms tie CPU allocation to memory configuration. Increasing memory can shorten class loading, processing, and compression/decompression, though it also raises cost per unit of time. Benchmark configuration tiers rather than defaulting to the highest one.
- **AOT or GraalVM Native Image:** can reduce startup time and memory footprint for some workloads. In return, builds become more complex, requiring reflection/resource configuration and compatibility testing for libraries, instrumentation, TLS, and runtime behavior.
- **Runtime snapshot/restore:** some providers support snapshotting initialized state for fast restoration. You must verify post-restore hooks, clocks, entropy, unique IDs, credentials, and network connections. Never assume sockets or credentials inside a snapshot remain valid after restore.
- **Provisioned/warm capacity:** keeps a pool of initialized environments ready to reduce cold starts within the configured capacity. This incurs cost for idle capacity and does not guarantee every burst fits within the provisioned level.
- **Reducing framework weight or using a lighter runtime:** can help, but must be balanced against maintainability, observability libraries, and development velocity.

Names, limits, and pricing models for snapshots, provisioned concurrency, or warm capacity vary by provider and runtime. Check current platform documentation before deploying to production.

### 6.3. Do Not Rely on Artificial Warm-Ups

Sending periodic requests to "keep a function warm" does not guarantee real requests will hit the same environment. The platform can reclaim environments or spin up additional ones as load rises. Warm-ups also generate invocations and cost, pollute metrics, may inadvertently trigger downstream calls, and mask true scale-from-zero behavior.

If SLOs require low startup latency, use platform-supported capacity mechanisms and measure the cost. If a workload has steady, predictable traffic and strict latency requirements, compare FaaS against an always-on container/worker service. Base the decision on end-to-end latency, utilization, operability, and total cost.

## 7. Reduce Downstream Latency

### 7.1. Reduce Call Count and Shorten the Critical Path

- Eliminate N+1 queries and duplicate HTTP calls.
- Fetch all required data in a single properly indexed query instead of multiple sequential calls.
- Run calls in parallel only when branches are independent and downstream systems have sufficient capacity.
- Bound concurrent calls; do not spawn an unbounded thread or future per item in a payload.
- Paginate large datasets and cap response sizes.
- Cache read-heavy, infrequently changing data when consistency requirements allow.

Parallelization can reduce single-request latency while increasing peak load on downstream systems. Before using `CompletableFuture` or fan-out, set concurrency limits, timeouts, and cancellation rules for remaining branches when the request deadline expires. A dedicated thread pool must have a bounded size and be safely reused within the environment.

In-memory caching inside an environment is local only; it can vanish when the environment is reclaimed and is not shared across environments. If sharing across instances is needed, use an external cache. Both cache types need TTLs, invalidation rules, and protection against cache stampedes when many environments miss simultaneously.

### 7.2. Optimize the Database

When traces show the database dominates latency, inspect query plans and actual rows scanned. Focus on:

- Indexes matching common filter predicates, sort orders, and joins.
- Avoiding `SELECT *` when responses only need a few columns.
- Avoiding N+1 queries and repeated queries inside loops.
- Keeping transactions short; do not wait on external APIs while holding locks.
- Using bounded pagination with deterministic ordering.
- Checking lock wait, I/O, CPU, replication lag, and database connection limits.

A query that is fast in dev can be slow in production due to data volume, value distribution, indexes, concurrency, and locks. Test on realistic data and inspect execution plans before modifying indexes.

### 7.3. Optimize Network Connections and HTTP Services

Separate pool wait, DNS, connect, TLS, and remote processing times. If the first request after idle is slow while subsequent requests are fast, check keep-alive, DNS caching, connection lifetime, and TLS handshakes. If every request is slow, inspect server-side latency, region, network routing, and response size.

In VPC or private network environments, check route tables, security groups/firewalls, NAT/egress gateways, DNS resolvers, and private endpoints. Do not assume all delays inside a VPC are cold starts. With AWS Lambda or similar platforms, network attachment mechanisms and how providers allocate interfaces have evolved over time; measure the actual network path and consult current provider documentation.

Prefer calling services in nearby regions when data requirements and redundancy allow. Check for hairpinning through public endpoints when a suitable private endpoint exists. Do not disable TLS or relax network permissions to save a few milliseconds; optimize connection reuse, endpoints, and safe DNS configuration instead.

### 7.4. Control Pools and Concurrency

Function concurrency and downstream capacity must be designed together. If a database can only handle 300 connections and each environment can open 5 connections, the number of concurrent environments must be accounted for alongside other services sharing that database.

Common measures include:

- Capping function concurrency according to downstream capacity.
- Keeping pool sizes small, setting explicit acquisition timeouts, and measuring active/pending connections.
- Using a database proxy or pooler when appropriate for the database engine.
- Reducing connection hold time and transaction duration.
- Using queues to absorb bursts for work that can be processed asynchronously.
- Using bulkheads or semaphores to cap load per dependency.

A circuit breaker placed inside an execution environment holds local state only. When the platform creates multiple environments, each environment can have a different breaker state. Thus, a local circuit breaker helps stop one instance from hammering a failing dependency, but it does not replace system-wide rate limiting or load control.

## 8. Timeouts, Retries, and Idempotency

### 8.1. Design Timeouts Around a Shared Deadline

A request typically traverses a client, gateway, function, and multiple downstream systems. Each layer's timeout should align with the remaining deadline. Illustrative example:

| Layer | Example budget |
|---|---:|
| Client timeout | 3.0 seconds |
| Gateway integration timeout | 2.5 seconds |
| Target function timeout | 2.2 seconds |
| One critical downstream call | max 1.2 seconds |
| Remaining budget | validation, logic, response, and buffer |

These numbers merely illustrate budget allocation. Actual gateway and function limits depend on the provider. For synchronous APIs, the function must finish before the gateway disconnects, and the client should wait reasonably longer than the gateway to receive a controlled error response. If the function timeout is longer than the gateway timeout, the gateway may return an error to the client while the function keeps running and consuming resources.

Propagate the deadline or remaining time downstream instead of letting every service start a fresh full timeout. If an invocation has only 400 ms left, do not initiate a downstream request with a 1-second timeout. When close to the deadline, stop unnecessary work and return a classified error.

### 8.2. Bounded Retries

Retries are only appropriate for transient errors likely to succeed on retry, such as connection resets, certain 5xx responses, or 429s per service policy. Do not retry validation, authorization, or malformed request errors. Respect `Retry-After` if the service provides it.

A retry policy should include:

- A small maximum attempt count and total elapsed time within the deadline.
- Exponential backoff with jitter so many invocations do not retry in lockstep.
- Classification of retryable versus non-retryable errors.
- Limiting retries to an appropriate single layer; avoid having client, gateway, function, and SDK all retry independently.
- Metrics/logs clearly recording attempts, error types, and time consumed.

Retries can amplify incidents. For example, 100 requests/second, each retrying twice, can generate up to 300 downstream calls/second in the worst case. When a downstream system is overloaded, aggressive retries lengthen queues and prolong outages.

### 8.3. Ensure Idempotency When Requests Can Be Resent

HTTP clients can time out even after the server completed the operation; message brokers can redeliver messages; platforms can retry invocations depending on configuration. Therefore, a request processed multiple times must not produce unintended duplicate business transactions.

- For write operations, accept an idempotency key or stable business key from the caller.
- Store processing state and results in a durable store using unique constraints or conditional writes.
- Update state and business side effects in the same transaction when possible.
- Use outbox/inbox patterns or deduplication mechanisms when coordinating databases and message brokers.
- Set TTL and key retention policies matching the maximum retry/redelivery window.
- Do not use a `static Map` in Java as an idempotency store; that map is not shared across environments and disappears when an instance is reclaimed.

If an operation cannot be made idempotent, clearly define the uncertain state after a timeout and establish a reconciliation process. Do not automatically retry a payment or order-creation operation simply because the client did not receive a response.

## 9. Cold Start, Scaling, and Cost

Serverless creates additional environments as concurrency increases. A traffic burst can simultaneously trigger many cold starts and many new connections to downstream systems. Consequently, reducing cold starts in isolation while ignoring database limits can worsen p99 under higher load.

Evaluate options using data:

| Option | Expected impact | Costs/risks to consider |
|---|---|---|
| Reduce dependencies and init work | Reduces startup time for new environments | Refactoring effort, library compatibility |
| Increase memory/CPU | Can reduce init and compute time | Cost per invocation increases; requires benchmarking |
| Snapshot/AOT/native image | Can reduce startup | Build, debugging, reflection, restore semantics, and compatibility |
| Provisioned/warm capacity | Reduces cold starts within provisioned capacity | Pays for idle capacity; bursts beyond capacity can still go cold |
| Limit concurrency | Protects downstream systems, reduces connection storms | Can increase queue age or throttling |
| Queue and asynchronous workers | Absorbs bursts, decouples API from long work | Adds complexity, completion latency, and idempotency requirements |
| Move to an always-on service | Keeps runtime and connections steadier | Requires managing capacity, scaling, patching, and idle cost |

Total cost is not just function runtime. Include invocations, memory/CPU, provisioned capacity, gateway, logging/tracing, NAT/egress, database connections/proxies, caches, and retries. A faster function that creates more connections or retries can raise total system cost.

When deciding whether to keep using FaaS, consider: are requests short and independent enough; can downstream systems handle variable concurrency; does cold-start latency stay within the SLO after optimization; and is retry behavior safe. If latency requirements are strict while traffic is steady, provisioned capacity or an always-on service may make more sense. If most time is spent in database queries, moving off FaaS will not automatically make queries faster.

## 10. Runbook for Investigating Slow APIs

The table below serves as an initial incident triage sequence.

| Symptom | Check first | Informed action |
|---|---|---|
| p99 rises while init duration rises concurrently | Cold/warm split, new environment count, package/runtime changes | Measure init components; reduce dependencies or consider suitable capacity/snapshots |
| Warm requests are slow with long DB spans | Query plan, lock wait, pool wait, connection count | Optimize queries/indexes, transactions, poolers, and concurrency |
| Warm requests are slow with long HTTP spans | DNS/connect/TLS, remote span, response size, retries | Reuse clients/connections, check region, and address remote service bottlenecks |
| Pool wait rises as concurrency increases | Pool pending, environment count, database limits | Limit concurrency, tune pools, or use a proxy |
| Gateway times out while function keeps running | Gateway/function timeouts and downstream deadlines | Align timeouts, propagate deadlines, cancel unneeded work |
| 429/5xx and attempts spike rapidly | Retries at client, SDK, function, and gateway | Bound retries, add backoff+jitter, rate limit, and enforce idempotency |
| Function is fast but client is slow | Gateway, queue, DNS, TLS, and client network | Separate per-layer metrics; investigate edge/network |
| Slow after idle, next request is fast | Connection resets, DNS/TLS, init duration | Check connection lifetime and reconnect safely |

During an active incident:

1. Confirm affected route, region, version, start time, and SLO.
2. Inspect error rate, p95/p99, throttling, concurrency, and queue age.
3. Pull several representative slow traces, including both requests with init and warm requests.
4. Identify the stage on the critical path; verify downstream capacity before increasing concurrency.
5. If immediate mitigation is needed, consider rate limiting, reducing fan-out, temporarily disabling non-essential branches, or offloading long work to a queue per the service runbook.
6. After stabilizing, confirm the root cause with a small measurable change, document the findings, and update alerts.

Do not raise timeouts indefinitely just to make visible errors disappear. Long timeouts hold invocations and connections longer, increasing concurrency and cost. If you must temporarily increase a timeout, check limits in all remaining layers and monitor resource hold times.

## 11. Investigation Example

Suppose the `GET /orders/{id}` API has p50 at 130 ms, p95 at 420 ms, and p99 at 2.8 seconds. The rate of requests breaching the 800 ms SLO spikes after a traffic burst.

**Initial observation:** function duration in the p99 group is high, yet not every slow request has an init duration. Requests with init duration typically take around 1.6–2.0 seconds; the warm group still contains several requests near 2 seconds.

**Reading warm traces:** several requests spend 1.7 seconds in `orders-db.query`; remaining spans are under 100 ms. Database metrics show query execution time is stable, while pool pending rises sharply as concurrency climbs. This indicates at least two issues: cold starts slow down the first request of new environments, and pool waits slow down warm requests during bursts.

**Hypothesis and tests:**

1. Measure pool acquisition and query execution separately to confirm pool wait time.
2. Reduce per-environment pool size and set a concurrency limit matched to database capacity; monitor queue age and p99.
3. Evaluate using a database proxy/pooler to share connections more effectively.
4. Measure the init breakdown and strip unnecessary dependencies from the Java handler.
5. Only after measuring the cold-start contribution, test increasing memory or provisioned capacity over a controlled period.

**Results to prove:** pool wait drops, database connections stay below threshold, warm p99 improves, cold p99 drops within provisioned capacity, errors/throttles do not rise, and total cost remains within budget. If only cold p99 improves while warm p99 stays high, the downstream issue remains unresolved.

This example shows that an API can suffer from multiple latency causes simultaneously. You must segment requests and measure each stage to avoid treating every slow request as a cold start.

## 12. Testing and Preventing Regressions

### 12.1. Testing Cold and Warm Paths

- Deploy the new version to a staging environment configured close to production.
- Record init duration of new environments and first-request latency.
- Send multiple follow-up requests to observe the warm path, without assuming the platform keeps a single environment.
- Generate controlled bursts to observe new environment count, concurrency, pool wait, and downstream saturation.
- Repeat across relevant regions and network configurations.

Cold starts cannot be proven with unit tests running in a local JVM. Unit tests are useful for logic and instrumentation; cold starts must be measured on an actual serverless runtime. Load tests must be bounded with controlled test data so they do not overload shared systems.

### 12.2. Testing Downstream Behavior and Retries

- Use stubs or fault injection to simulate timeouts, connection resets, 429s, and 5xx errors.
- Verify requests stop when the deadline expires and do not trigger infinite retries.
- Resend the same idempotency key repeatedly to confirm business side effects occur only once.
- Simulate slow databases, exhausted pools, and lock contention in a safe environment.
- Test large responses, pagination, and fan-out to measure memory and concurrency impact.

### 12.3. Recommended Alerts

- p95/p99 or SLO breach rate by route.
- Error rate, timeouts, throttles, and queue/event age.
- Init duration or cold invocation ratio if supported by the provider.
- Pool wait, connection count, and query latency for critical databases.
- Downstream HTTP latency, retry rate, 429/5xx, and circuit-breaker state.
- Concurrency and cost by function/service.

Alerts need thresholds, sustained evaluation windows, and links to dashboards/traces. A brief spike may not warrant paging, whereas sustained SLO breaches require alerting. Do not create alerts per request or per user ID.

## 13. Pre-Closure Investigation Checklist

- [ ] Confirmed affected route, region, version, time window, and SLO.
- [ ] Examined p50, p95, p99, and SLO breach rate rather than averages alone.
- [ ] Separated cold-start requests from warm requests using verifiable signals.
- [ ] Compared client, gateway, function, and downstream timings on the same requests.
- [ ] Identified the span or stage dominating the critical path.
- [ ] Measured pool wait, connect/TLS, remote processing, and retries separately where relevant.
- [ ] Checked function concurrency against database/backend service capacity.
- [ ] Configured finite timeouts and bounded retries aligned with the deadline.
- [ ] Verified idempotency for operations that may be resent.
- [ ] Tested cold, warm, steady load, and burst traffic in an appropriate environment.
- [ ] Compared latency, error rate, throttling, downstream health, and total cost after changes.
- [ ] Recorded representative traces/logs, root cause, changes, and results in the incident record.

## Conclusion

Investigating slow serverless APIs must start from end-to-end data. Cold starts show up in Java environment initialization costs and mainly impact first requests; downstream latency shows up in connection wait or backend service processing and can affect warm requests as well. Metrics reveal trends, logs correlate events, and traces pinpoint the stage on the critical path.

Once the root cause is identified, optimize the right layer: reduce init work or provision capacity for cold starts; reuse clients, improve pools/queries, cap concurrency, and bound retries for downstream dependencies. Every change must be validated against percentiles, SLOs, dependency health, and total cost. This provides the evidence needed to decide whether to continue with FaaS, add always-ready capacity, or move part of the workload to an always-on model.

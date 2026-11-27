# Investigating a Slow Request

When a Spring Boot request responds slowly, looking only at error logs or average duration is rarely enough to find the root cause. Metrics show how many requests latency affects and when it started; distributed traces show where time is consumed across services and operations; logs provide request-specific details to confirm what happened. Combining these three signals takes you from symptom to evidence-backed root cause.

This practice exercise simulates an incident in an ordering system. The checkout API responds slowly while CPU and error rates remain normal. You will use Micrometer metrics, trace context, and log correlation to trace the request across services, identify a slow inventory supplier call, and uncover a transaction holding a database connection while waiting on HTTP. At the end, you will propose a fix and post-deployment verification criteria.

## Practice Objectives

After this lesson, you will be able to:

- Identify the start time and blast radius of a latency spike using metrics.
- Pick a representative trace and read parent-child relationships, durations, timestamps, and span attributes.
- Use a trace ID to correlate logs belonging to the same request across multiple services.
- Distinguish slow database queries, slow downstream services, and connection pool saturation.
- Propose a testable change, then verify it after deployment using the same set of signals.

## Incident Context

The system has three core services. Users call checkout to view order details; checkout reads order data, calls inventory to check stock, and calls pricing to fetch current prices.

~~~mermaid
flowchart LR
    U[Client] --> C[checkout-api]
    C --> I[inventory-service]
    C --> P[pricing-service]
    I --> DB[(Inventory DB)]
    I --> S[Supplier API]
    C -. metrics, logs, traces .-> O[Observability backend]
    I -. metrics, logs, traces .-> O
    P -. metrics, logs, traces .-> O
~~~

Over the last 10 minutes, the dashboard recorded:

| Metric | Baseline | Current |
| --- | ---: | ---: |
| checkout GET p50 | 85 ms | 110 ms |
| checkout GET p95 | 240 ms | 1.8 s |
| checkout GET p99 | 420 ms | 3.5 s |
| HTTP 5xx | 0.3% | 0.4% |
| checkout CPU | 42% | 45% |
| inventory CPU | 39% | 41% |

Latency at p95 and p99 rose sharply while error rate and CPU stayed nearly flat. This signals that a subset of requests is waiting on a resource or dependency; low CPU does not mean an application is healthy if threads are blocked waiting on I/O, connections, or locks.

A specific request was recorded with the following details:

- Route: GET /api/orders/{id}
- Receiving service: checkout-api
- Trace ID: 4f6c2d8e9a104c3fb78a2e5c1d9a7b21
- Total duration: roughly 3.42 seconds
- HTTP outcome: 200

The ID in this example is illustrative only. In real environments, never put order IDs, user IDs, or personal data into metric tags. Use trace IDs to look up requests and display business identifiers only where data policy permits.

## Step 1: Narrow Down with Metrics

Before opening an individual trace, confirm the incident has broad enough scope to explain the alert. Check latency by service, route, method, and status; then compare request rate, error rate, resources, and dependencies.

To obtain the telemetry illustrated below, the application needs Actuator, the Prometheus registry, and the matching tracing bridge/exporter. A minimal starting configuration looks like:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
  tracing:
    sampling:
      probability: 0.1
~~~

Only expose management endpoints inside protected networks and scopes. The sampling rate 0.1 is an illustrative example; choose a value based on traffic, cost, and investigation needs. Low sampling may miss rare slow requests, whereas high sampling increases trace ingestion and storage volume.

If Prometheus receives histograms from Micrometer, you can compute HTTP server request p95 with the following query. Actual metric names and labels depend on the registry, conventions, and configuration version:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri="/api/orders/{id}",
      method="GET"
    }[5m])
  )
)
~~~

Compare against p99 and error ratio:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri="/api/orders/{id}",
      method="GET"
    }[5m])
  )
)
~~~

~~~promql
sum(rate(http_server_requests_seconds_count{
  uri="/api/orders/{id}",
  method="GET",
  status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  uri="/api/orders/{id}",
  method="GET"
}[5m]))
~~~

Histograms must be enabled and scraped properly for quantile queries to have valid data. If you only have timer count/sum, you can calculate throughput and average latency, but you cannot derive accurate p95 or p99 from those two values. Never rely on average to conclude that slow requests have disappeared.

Inspect a meter directly via Actuator when the endpoint is exposed and appropriately secured:

~~~bash
curl -G "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/api/orders/{id}" \
  --data-urlencode "tag=method:GET"
~~~

The Actuator response tells you whether the meter exists, which tags are available, and count/total statistics for that meter. This checks a single instance; Prometheus dashboards or a metrics backend are still required for cluster-wide trends.

Next, compare latencies across services and dependencies over the same time window. In this scenario, checkout slows down at the same time inventory slows down; pricing stays near baseline. That lets us prioritize checking the inventory branch before inspecting checkout's database or gateway serialization.

## Step 2: Pick a Useful Trace

Open the trace matching the trace ID retrieved from request logs or your observability tool. Inspect the service, operation, start time, total duration, status, and child spans. Select a slow trace from the affected route, version, and time window; then compare it against a normal trace for the same route.

An illustrative trace for the request has this structure:

| Span | Service | Duration |
| --- | --- | ---: |
| HTTP GET /api/orders/{id} | checkout-api | 3,420 ms |
| order.repository.findById | checkout-api | 18 ms |
| HTTP GET /api/inventory/{sku} | checkout-api → inventory-service | 3,150 ms |
| HTTP GET /api/prices/{sku} | checkout-api → pricing-service | 42 ms |

The three branches do not necessarily run sequentially in every application. When reading a waterfall, rely on start timestamps and end times to determine which spans actually lie on the critical path. Never add durations of parallel spans and treat the sum as request time.

The inventory call accounts for nearly all of the request time. Expand the trace on the inventory side via the context propagated over HTTP. The breakdown inside that service shows:

| Operation in inventory | Duration |
| --- | ---: |
| inventory.lookup | 3,100 ms |
| inventory.repository.findStock | 16 ms |
| supplier.client.getStatus | 2,910 ms |
| Remaining processing | ~174 ms |

The database query took only 16 ms, whereas the Supplier API call took nearly 3 seconds. This rules out the hypothesis "the primary SQL query is the main bottleneck" for the inspected request. It also pinpoints which dependency needs deeper investigation.

While reading the trace, also check:

- Parent-child: does the client span link properly to the server span on the target service?
- Propagation: is the trace ID preserved across the HTTP boundary, or did the trace split into two independent trees? With properly instrumented HTTP clients/servers, Micrometer Tracing can inject/extract context using formats such as W3C traceparent.
- Status and events: are there exceptions, timeouts, retries, or unusual events on the spans?
- Attributes: are method, route template, peer service, status code, and version sufficient for classification?
- Sampling: was the inspected trace sampled according to the current configuration?

A single trace explains the execution path of one request, but does not prove all traffic shares the exact same cause. Use metrics to gauge prevalence and traces to understand path details.

## Step 3: Correlate Logs with the Trace ID

After identifying the slow Supplier API span, search logs for the exact trace to inspect timeouts, retries, response status, and timestamps. Services must write trace ID and span ID into the logging context. When using Micrometer Tracing, these values can be populated into MDC; the logging pattern must keep them in the output.

Example level pattern for Logback:

~~~yaml
logging:
  pattern:
    level: "%5p [%X{traceId:-},%X{spanId:-}]"
~~~

If using a JSON encoder or another log collector, map the equivalent values to structured fields such as service, trace_id, span_id, event, and duration_ms. Field names may vary across pipelines; align on the schema mapping before querying.

Sample log from the same trace:

~~~json
{
  "timestamp": "2026-11-22T07:18:31.420Z",
  "level": "WARN",
  "service": "inventory-service",
  "event": "supplier.request.slow",
  "duration_ms": 2910,
  "http_method": "GET",
  "http_status": 200,
  "trace_id": "4f6c2d8e9a104c3fb78a2e5c1d9a7b21",
  "span_id": "8d7a1c2e3f4b5a60"
}
~~~

Query logs by trace ID in your logging system, logically expressed as:

~~~text
trace_id = "4f6c2d8e9a104c3fb78a2e5c1d9a7b21"
~~~

Read logs ordered by timestamp and span ID to preserve execution sequence. A single trace may produce multiple logs across multiple services; trace ID ties them to the same request, while span ID identifies which operation emitted each log. If logs lack trace IDs, check MDC configuration, log patterns/encoders, and whether context was lost when handing off to another executor or thread.

Do not add trace IDs to metric tags. Trace IDs are nearly unique per request, causing cardinality to grow with traffic. Use trace IDs in traces and logs; metrics should only use dimensions with finite value sets such as service, route template, method, status, or outcome.

## Step 4: Inspect the Connection Pool and Transactions

Logs show the Supplier API responded slowly yet the request still succeeded. To find out whether this slowness spills over to other requests, check HikariCP metrics in inventory over the same time window:

| Metric | Observed |
| --- | ---: |
| hikaricp.connections.max | 20 |
| hikaricp.connections.active | 20 |
| hikaricp.connections.idle | 0 |
| hikaricp.connections.pending | 17 |
| hikaricp.connections.acquire p95 | 2.8 s |

Active connections hitting max, idle dropping to 0, and pending rising indicate requests are waiting for connections. Elevated acquire duration confirms connection acquisition time is a real bottleneck during this period; timer p95 is only queryable when corresponding histograms or percentiles are configured. Prometheus metric names may use underscores, such as hikaricp_connections_active; check the exact names and tags exported by your registry.

These metrics tell you the pool is saturated, but do not by themselves explain why connections are held so long. Cross-check code paths and traced operations against transaction boundaries. Suppose current code looks like:

~~~java
@Service
public class InventoryService {
    private final StockRepository stockRepository;
    private final SupplierClient supplierClient;

    public InventoryService(
            StockRepository stockRepository,
            SupplierClient supplierClient) {
        this.stockRepository = stockRepository;
        this.supplierClient = supplierClient;
    }

    @Transactional(readOnly = true)
    public InventoryView lookup(String sku) {
        Stock stock = stockRepository.findBySku(sku)
                .orElseThrow();
        SupplierStatus status = supplierClient.getStatus(sku);
        return new InventoryView(stock, status);
    }
}
~~~

The transaction spans both the database query and the HTTP call to the Supplier API. A connection acquired for the transaction can remain held while the thread waits for the network response. When the Supplier API is slow under concurrent load, long-held connections exhaust the pool; unrelated requests must queue for a connection. Thus, a single slow dependency amplifies into service-wide slowdowns across inventory.

The single-request trace showed the Supplier API directly consuming time. HikariCP metrics showed the pool saturating during the same window. Transaction boundaries in the code explain the causal link between those two symptoms. Keep these three findings distinct: the trace identifies the request's critical path; pool metrics reveal service-wide resource pressure; code explains how the resource is held.

## Step 5: Propose and Implement Changes

There are two issues to address. First, the Supplier API responds slowly so the current request still has to wait. Second, the transaction holds a DB connection while waiting on the network, turning dependency latency into connection pool starvation. Fixing transaction boundaries relieves pool pressure, but does not by itself speed up the Supplier API or guarantee lower request p95 if requests still wait on that same call.

For this read flow, isolate the transaction to the database read using a separate bean:

~~~java
@Service
public class StockReader {
    private final StockRepository stockRepository;

    public StockReader(StockRepository stockRepository) {
        this.stockRepository = stockRepository;
    }

    @Transactional(readOnly = true)
    public StockSnapshot find(String sku) {
        Stock stock = stockRepository.findBySku(sku)
                .orElseThrow();
        return new StockSnapshot(
                stock.getSku(),
                stock.getAvailableQuantity());
    }
}

public record StockSnapshot(String sku, int availableQuantity) {}
~~~

~~~java
@Service
public class InventoryService {
    private final StockReader stockReader;
    private final SupplierClient supplierClient;

    public InventoryService(
            StockReader stockReader,
            SupplierClient supplierClient) {
        this.stockReader = stockReader;
        this.supplierClient = supplierClient;
    }

    public InventoryView lookup(String sku) {
        StockSnapshot stock = stockReader.find(sku);
        SupplierStatus status = supplierClient.getStatus(sku);
        return new InventoryView(stock, status);
    }
}
~~~

StockReader is a separate bean so the call passes through the Spring transaction proxy. When find finishes, the read transaction completes before InventoryService calls the Supplier API. Avoid calling another @Transactional method inside the same object and expecting self-invocation to trigger the proxy.

Next, address Supplier API latency according to business requirements:

- Set bounded connect and response/read timeouts aligned with the parent request's latency budget.
- Use bulkheads or concurrency limits so one slow dependency cannot consume all processing threads.
- Use a circuit breaker if you need to stop calling a persistently failing dependency; explicitly verify whether a fallback response is business-safe.
- Retry only retryable errors, capping retry count and total retry duration; avoid synchronized retry storms when the Supplier API is already overloaded.
- Consider caching status data that tolerates staleness, with explicit TTL and invalidation rules.

Do not blindly increase max pool size. A larger pool pushes load onto the database, hides long-lived transactions holding connections, and increases concurrent queries. Only tune pool size after measuring required concurrency and database limits.

If business logic truly requires an atomic transaction spanning multiple steps, do not split transactions arbitrarily in ways that break correctness. Evaluate workflow design, sagas, outbox patterns, or compensating actions instead of holding a database connection across a long network call.

## Step 6: Verify After Changes

Deploy the change narrowly and compare a canary against the stable version under similar traffic. Keep the same dashboards, queries, and a window long enough to collect representative samples.

Expected signals:

| Signal | Result to Confirm |
| --- | --- |
| Inventory traces | Transaction ends right after database operation; supplier call sits outside transaction |
| HikariCP | Active is no longer pinned at max; pending drops; acquire p95 returns near baseline |
| Supplier client | Duration drops after dependency optimization, or timeout/fallback triggers within budget |
| checkout HTTP | p95/p99 drops once the critical path actually shortens |
| Logs | Trace ID/span ID still correlate across services; no abnormal spike in timeouts or retries |
| Error rate | No increase in business errors or timeout/fallback-induced errors |

If you only split the transaction while the Supplier API still takes nearly 3 seconds, HikariCP may recover while requests remain nearly as slow. If the Supplier API speeds up while the transaction still wraps the network call, the pool remains at risk of exhaustion under higher load. Verify each outcome independently to know which change solved which problem.

Roll back or halt rollout if error rates climb, business data becomes inconsistent, fallback changes behavior unexpectedly, or connection pools and latency worsen. Capture traces, dashboard snapshots, logs, and config versions for before/after comparison.

## Other Hypotheses to Rule Out

Not every slow request is caused by a downstream service or connection pool. Use signals across all three telemetry types to check other possibilities:

| Hypothesis | Signals in Metrics | Signals in Traces / Logs |
| --- | --- | --- |
| Slow SQL | DB query duration rises, DB load or lock wait rises | Long JDBC spans, slow query logs |
| Slow downstream | Client latency rises for a specific dependency | Long client span; target server span also long if propagation works |
| Pool starvation | Hikari active hits max, pending and acquire duration rise | Requests queue for resources; connection-holding operations may stretch |
| CPU or GC | High CPU, throttling, or rising GC pauses | Multiple spans inside the process slow down together; GC logs show matching pauses |
| Lock contention | Blocked/waiting threads rise, throughput drops | Span contains long lock wait; thread dumps help verify |
| Serialization or in-app processing | CPU/request or processing time rises despite stable dependencies | Long internal span with no matching client/DB spans |

If a trace does not appear, do not conclude the request never happened. The request might not have been sampled, trace context might not have propagated, or the exporter/backend might be failing. Use metrics to confirm traffic, check log correlation, and inspect exporter health before concluding. With head-based sampling, rare slow requests might be dropped; consider an appropriate sampling policy or tail sampling at the collector if the architecture supports it.

## Slow Request Investigation Checklist

- [ ] Identify the route, service, version, and time window with elevated latency.
- [ ] Check p50/p95/p99, request rate, and error rate; never inspect average alone.
- [ ] Compare services and dependencies to isolate the critical path.
- [ ] Open a slow trace and a normal trace for the same route side by side.
- [ ] Verify trace context propagates across service boundaries.
- [ ] Correlate logs by trace ID and use span ID to identify which operation emitted each log.
- [ ] Inspect connection pools, databases, threads, CPU, GC, and related resources.
- [ ] Cross-check metrics against code paths and transaction boundaries before concluding root cause.
- [ ] Propose a change with a clear hypothesis, rollback threshold, and verification metrics.
- [ ] After deployment, independently verify latency, error rate, resources, and telemetry quality.

A thorough investigation finishes with a verifiable chain of evidence: metrics establish scope and timing; traces point to operations on the critical path; logs fill in request-specific events; resource metrics and source code explain the slowdown mechanism. When all three signals align, operations teams can fix the true root cause and measure the impact of the change.

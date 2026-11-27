# Load Testing, Configuration Tuning, and API Service Handover

A Java serverless API is production-ready only when the team has proven it executes business logic correctly under expected load, keeps latency within SLOs, avoids overloading databases or downstream dependencies, meets cost targets, and has clear operational procedures. Sending a few successful test requests or benchmarking the Java handler in isolation is not enough to conclude the service can handle real traffic.

This lesson uses the **Amazon API Gateway + AWS Lambda Java + database** reference model. The same testing and handover principles apply to HTTP functions on Azure Functions, Google Cloud Run, or other serverless platforms. It covers three phases: designing and running load tests, tuning configuration from measured data, and handing the API service over to the operations team.

The expected outcome is an evidence-backed **capacity envelope**: how many requests per second the API sustains under tested conditions, what p95/p99 latencies look like, where concurrency and dependency limits lie, what each successful transaction costs, and what actions to take when thresholds are breached.

## 1. Objectives of Load Testing

Load testing evaluates system behavior when many requests arrive concurrently or continuously. For serverless systems, tests must cover the entire request path:

~~~mermaid
flowchart LR
    C["Load generator"] --> E["Internet / DNS / TLS"]
    E --> G["API Gateway"]
    G --> L["Java Lambda"]
    L --> D["Database / cache"]
    L --> X["External APIs"]
    L --> R["Response"]
    R --> C
    G --> M["API metrics"]
    L --> O["Logs / traces / metrics"]
    D --> P["Database metrics"]
~~~

Key objectives:

- Measure the throughput the API sustains under defined load conditions.
- Measure p50, p95, and p99 latency and error rates.
- Identify limits across API Gateway, Lambda concurrency, the Java runtime, databases, caches, or external APIs.
- Test behavior during rapid traffic ramps, sudden drops, or sustained multi-hour runs.
- Uncover memory pressure, thread contention, connection exhaustion, and cold starts.
- Verify timeouts, retries, rate limits, idempotency, and graceful degradation.
- Estimate costs at normal, peak, and burst traffic levels.
- Produce evidence to finalize production configuration and complete operational handover.

A test that calls Lambda directly via the Invoke API misses API Gateway latency and throttling. Conversely, hitting the external endpoint without observing Lambda and the database makes bottleneck isolation difficult. Test both end-to-end and layer by layer.

## 2. Defining SLOs and Success Criteria Before Testing

No single RPS or latency number fits every API. Business and engineering owners must align on SLOs based on user experience, business processing times, and dependency capabilities.

An SLO set may include:

| Metric | Meaning | Illustrative Example |
|---|---|---|
| Availability | Percentage of valid requests handled successfully | 99.9% monthly |
| p95 latency | 95% of requests complete faster than the threshold | Under 400 ms |
| p99 latency | 99% of requests complete faster than the threshold | Under 900 ms |
| Sustained throughput | Continuously maintained load | 300 RPS for 30 minutes |
| Burst throughput | Short-term traffic surge | 600 RPS for 1 minute |
| Error rate | Failure rate excluding expected business errors | Under 0.5% |
| Recovery time | Time to return to normal after a burst or dependency failure | Under 2 minutes |

These values are illustrative only. Define the exact denominator, request population, measurement window, counted errors, and exclusions. For example, HTTP 400 from invalid input may reflect proper API behavior, whereas HTTP 500 or timeouts represent service failures.

Distinguish between:

- **SLO:** internal service quality target.
- **SLI:** actual measurement used to evaluate an SLO.
- **SLA:** formal customer commitment, potentially tied to support or compensation terms.
- **Error budget:** allowable failures over a window under the SLO.

Never pick thresholds merely because a benchmark tool defaults to 500 ms. Derive them from user tolerance, caller deadlines, and downstream business step latencies.

## 3. Modeling a Realistic Workload

Before writing scripts, describe realistic traffic:

- Routes and the request share of each route.
- Ratio of GET, POST, PUT/PATCH, and DELETE.
- Request and response sizes.
- Record counts returned and pagination behavior.
- Share of requests requiring authentication or authorization.
- Cache hit/miss ratio where caching exists.
- Database and external API processing times.
- Average, peak, and burst traffic plus hourly/daily cycles.
- Tenants or clients with differing usage patterns.
- Successful requests, validation errors, and retries.

Example workload for an order management API:

| Route | Share | Characteristics | Primary Dependencies |
|---|---:|---|---|
| GET /products | 45% | Read-heavy, small payload | Cache, database |
| GET /orders/{id} | 25% | Keyed read | Database |
| POST /orders | 20% | Writes and inventory checks | Database, inventory API |
| PATCH /orders/{id} | 7% | Status update | Database |
| POST /orders/{id}/confirm | 3% | Business side effects | Database, payment API |

Do not test only one easy route and extrapolate to the whole API. Order-creation routes involve more dependencies and side effects than catalog reads. Test each critical route individually as well as a blended workload matching production proportions.

## 4. Types of Load Tests

| Test Type | Purpose | How to Run |
|---|---|---|
| Smoke test | Confirm environment and scripts work | A few requests or very low load |
| Baseline test | Measure performance at low load | Steady low load over a short window |
| Load test | Verify expected traffic | Sustain target RPS |
| Stress test | Find breaking points and degradation modes | Ramp load beyond expected levels |
| Spike test | Test sudden bursts | Jump rapidly from low to high load |
| Soak test | Uncover cumulative issues | Sustain load for several hours |
| Capacity test | Establish safe capacity ceiling | Step load up incrementally |
| Recovery test | Verify system recovery | Reduce load after exceeding limits or dependency failures |

Run smoke and baseline tests before any large test. Bound stress and spike tests by scope, quotas, and cost. Soak tests surface connection leaks, memory growth, cache bloat, log volume spikes, and time-delayed failures.

## 5. Preparing a Safe Test Environment

Load tests generate real requests and can create real data. Prefer a dedicated AWS account or isolated environment configured closely to production.

Before running:

1. Use dedicated API stages and Lambda aliases for load testing.
2. Use isolated test databases, caches, and queues.
3. Use synthetic tenants and accounts.
4. Use sandboxes or stubs for payment, email, and SMS providers.
5. Disable or isolate unnecessary side effects.
6. Set billing alarms and test spending caps.
7. Check Service Quotas for API Gateway, Lambda, databases, and dependencies.
8. Confirm load generators have sufficient CPU, networking, and workers.
9. Define automatic abort thresholds and an accountable owner.
10. Prepare post-test data cleanup.

AWS recommends isolating load tests from production to avoid consuming live workload quotas or touching customer data. If an organization must test in production, require explicit approvals, maintenance windows, rate caps, dedicated test tenants, live monitoring, and an immediate kill switch.

Never embed PII or production credentials in scripts. Supply tokens via the CI/load generator secret store and never print them to logs.

## 6. Preparing Test Data and Valid Requests

Test data must reflect realistic sizes and distributions:

- IDs distributed broadly enough to avoid artificial hot keys.
- Small, medium, and large payloads.
- Diverse business states.
- Records with production-like relationships and indexes.
- Tenants with varying data footprints.
- Valid requests mixed with a small proportion of intentional error requests.

If every request reads the exact same record, caches can mask database bottlenecks. If every request writes the same key, tests create unrepresentative lock contention. Seed dedicated datasets and record initial cache state before each run.

For POST/PATCH, generate a unique idempotency key per logical operation. When a client retries, reuse that operation's key. Never share a single key across all virtual users, or the API will deduplicate requests and under-load the backend.

After the test, verify the actual count of created, updated, or deleted records rather than relying solely on 2xx responses reported by the load generator.

## 7. Choosing a Load Testing Tool

Common choices:

| Tool | Best Fit |
|---|---|
| k6 | JavaScript scripting, arrival-rate executors, thresholds, and CI integration |
| Gatling | Complex scenarios, user behavior modeling, and rich reporting |
| JMeter | GUI test plans, diverse protocols, and broad plugin ecosystem |
| Locust | Python scripts and custom user behaviors |
| Distributed Load Testing on AWS | Running distributed load generators natively on AWS |

Regardless of tool, distinguish **closed workloads** from **open workloads**:

- Closed workloads maintain a fixed number of virtual users; when the server slows down, the request emission rate drops accordingly.
- Open workloads fix the arrival rate independently; when the server slows down, requests keep arriving on schedule, making them better suited to verifying a target RPS.

If your target is 500 requests/second, arrival-rate tests verify the system actually sustains near 500 requests/second. Under closed workloads, slow responses throttle the generator and hide overload.

## 8. k6 API Load Testing Example

The example below submits order-creation requests at a constant arrival rate. URLs and tokens come from environment variables; never hard-code credentials in scripts.

~~~javascript
import http from "k6/http";
import { check } from "k6";
import { Rate } from "k6/metrics";

const businessSuccess = new Rate("business_success");

export const options = {
  scenarios: {
    steady_load: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.TARGET_RPS || 100),
      timeUnit: "1s",
      duration: __ENV.DURATION || "5m",
      preAllocatedVUs: 50,
      maxVUs: 200
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500", "p(99)<1000"],
    dropped_iterations: ["count==0"],
    business_success: ["rate>0.995"]
  }
};

export default function () {
  const operationId = "load-" + __VU + "-" + __ITER;

  const payload = JSON.stringify({
    customerId: "load-test-customer-" + __VU,
    items: [
      {
        sku: "TEST-SKU-" + __VU,
        quantity: 1
      }
    ]
  });

  const response = http.post(
    __ENV.API_BASE_URL + "/orders",
    payload,
    {
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + __ENV.API_TOKEN,
        "Idempotency-Key": operationId
      },
      tags: {
        route: "POST /orders"
      }
    }
  );

  const httpAccepted = check(response, {
    "response is successful": (r) =>
      r.status >= 200 && r.status < 300
  });

  let businessOk = false;
  if (httpAccepted) {
    try {
      const body = response.json();
      businessOk = Boolean(body.orderId) && body.status === "CREATED";
    } catch (error) {
      businessOk = false;
    }
  }
  businessSuccess.add(businessOk);
}
~~~

Thresholds in this example are illustrative; replace them with your API's SLOs. Pre-seed test customers and SKUs matching the VU count—having every VU write to one record creates artificial hot-key contention. Ensure test inventory covers total iterations or reset data between runs; running out of stock turns business errors into misleading capacity failures. The example checks HTTP status, `orderId`, and business status `CREATED`. If an endpoint returns `202 Accepted` for async work, verify the response contract and track downstream completion rather than treating `202` as completed business work.

Running the example:

~~~bash
k6 run \
  -e API_BASE_URL=https://load-test.example.com \
  -e TARGET_RPS=100 \
  -e DURATION=5m \
  api-load.js
~~~

Provide `API_TOKEN` via the runner or CI secret environment. Never write tokens into script files, command history, or test reports.

If the API enforces per-client or per-tenant rate limits, a single token shared across all VUs tests only one client's quota. Create a pool of test identities reflecting production traffic distribution while keeping all credentials in a secret store.

If k6 reports dropped iterations, the generator failed to maintain the scheduled rate. Increase `preAllocatedVUs`/`maxVUs` or add load generators and rerun. Never conclude the API cannot sustain 100 RPS if the generator only emitted 70 RPS.

## 9. Designing a Per-Run Test Profile

A test plan can be structured in phases:

~~~text
Phase 1: Warm-up
  10 RPS for 2 minutes

Phase 2: Baseline
  25 RPS for 5 minutes

Phase 3: Expected load
  100 RPS for 15 minutes

Phase 4: Peak load
  200 RPS for 10 minutes

Phase 5: Spike
  400 RPS for 1 minute

Phase 6: Recovery
  25 RPS for 5 minutes
~~~

This is an illustrative profile only. Substitute your service's traffic forecast, real peaks, and SLOs. Add a 1–4 hour soak test after shorter load tests pass.

Each phase must run long enough for metrics to stabilize. Record exact start and end timestamps for every phase to correlate against CloudWatch and application logs.

## 10. Separating Warm Requests from Cold Starts

For Java Lambda, measure both the first invocation and subsequent invocations after the execution environment is reused.

Factors affecting startup:

- JVM startup.
- Class loading and static initialization.
- Framework bootstrap.
- Dependency injection.
- AWS SDK client creation.
- Database connections.
- Deployment package size.
- Runtime and architecture.

Never fold an isolated cold start into average latency and conclude the whole API is slow. Record `Init Duration` from Lambda logs and analyze initialized requests separately.

Ways to reduce startup time:

- Remove unnecessary dependencies.
- Choose frameworks and DI containers with fast startup profiles.
- Initialize shared clients outside the handler.
- Avoid network calls or heavy queries in static initializers.
- Use SnapStart or Provisioned Concurrency where supported by your workload and runtime after measuring cost and impact.
- Optimize package/JAR size and deployment structure.

In Java, initializing SDK clients and database connection pools outside the handler lets them be reused across invocations within the same execution environment. Never store request state or sensitive data in global mutable state.

## 11. Estimating Concurrency from Request Rate and Duration

Concurrency is the number of requests executing simultaneously. Estimation formula:

\[
Concurrency \approx RPS \times AverageDurationSeconds
\]

For example, an API receiving 250 RPS with an average Lambda duration of 0.24 seconds:

\[
250 \times 0.24 = 60
\]

Estimated average concurrency is 60. When duration climbs because the database slows down, concurrency climbs even when RPS stays constant.

Use peak RPS and measured load-test duration for sizing. Average formulas do not replace testing bursts, tail latency, scaling rates, and quotas. Calculate separately per function if API routes are split across multiple Lambdas.

Do not confuse RPS with concurrency. A function with 50 ms duration handles far more requests per second per environment than a 1-second function, yet remains bounded by concurrency and request-rate quotas.

## 12. Checking API Gateway Quotas

API Gateway enforces account/Region throttling and may also impose stage- or route-level limits. Throttling uses a token bucket with rate and burst targets; exceeding them returns HTTP 429 to clients.

Throttle settings are best-effort targets, not strict hard ceilings. Check AWS quotas, account-level quotas, and route-level settings; never infer true capacity solely from a stage configuration field.

Before load testing, check:

- API type: HTTP API, REST API, or WebSocket API.
- Account-level throttle quotas in the target Region.
- Configured route/stage throttling.
- Usage plans or client-level limits if using API keys.
- Service quotas and AWS-enforced limits.
- Whether other APIs in the same account/Region share those quotas.

Never hard-code default documentation quotas as guaranteed capacity. Quotas vary by Region and account profile and can change over time. Verify Service Quotas and live configuration before testing.

Throttling is a protective control. Never raise limits just to make a test pass if Lambda or the database cannot absorb that load.

## 13. Checking Lambda Concurrency and Scaling

Lambda scales execution environments with concurrent requests, subject to account quotas, function concurrency limits, and scale-up rates.

Monitor:

- `ConcurrentExecutions`.
- `UnreservedConcurrentExecutions`.
- `Throttles`.
- `Invocations` and `Errors`.
- `Duration`.
- `ProvisionedConcurrencySpilloverInvocations` when using PC.
- `ClaimedAccountConcurrency` when analyzing account capacity.

Reserved Concurrency caps a function's maximum concurrency and reserves that pool for the function. It does not pre-warm execution environments.

Provisioned Concurrency pre-initializes execution environments. Use it when cold starts impact SLOs and capacity can be sized around baseline traffic. PC carries dedicated charges, and invocations exceeding provisioned capacity still run on standard concurrency.

Before requesting quota increases, verify whether Lambda is truly the bottleneck or whether the constraint is the database or a partner API. Raising concurrency can overwhelm downstream dependencies faster.

## 14. Tuning API Gateway

Settings to review:

- Route-level throttling rate and burst limits.
- Request/response payload sizes.
- Integration timeouts and client timeouts.
- Access logging and execution logging.
- Detailed route-level metrics.
- Caching when using REST APIs and supported routes.
- Authentication/authorizer latency.
- WAF or edge layers if present.
- Custom domains, TLS, and DNS paths.

API Gateway exposes `Latency` and `IntegrationLatency`. `Latency` measures total time from receiving the request to returning the response; `IntegrationLatency` measures time spent waiting on the backend. The gap reveals gateway, authorizer, and routing overhead.

Detailed route metrics can add CloudWatch costs. Enable them selectively for routes needing diagnostics or during investigations, then review afterward.

Example setting route throttling on an HTTP API:

~~~bash
aws apigatewayv2 update-stage \
  --api-id API_ID \
  --stage-name prod \
  --route-settings '{"POST /orders":{"ThrottlingBurstLimit":50,"ThrottlingRateLimit":100}}'
~~~

Values of 50 burst and 100 RPS are illustrative. Substitute limits validated against Lambda and downstream systems. Throttling limits are best-effort targets; never treat them as hard real-time guarantees.

## 15. Tuning Memory and CPU for Java Lambda

AWS Lambda allocates CPU proportionally to memory. Increasing memory can therefore speed up Java execution when workloads are bounded by CPU, class loading, or serialization.

A benchmarking workflow:

1. Select candidate memory tiers—e.g., 512, 1,024, 1,769, and 3,072 MB.
2. Keep the artifact, payload, dependencies, and traffic identical.
3. Run warm tests and cold-start tests separately.
4. Measure Duration, Max Memory Used, and error rates.
5. Calculate GB-seconds and cost per successful request.
6. Choose the configuration that meets SLOs at an acceptable total cost.

At 1,769 MB, Lambda allocates CPU equivalent to one vCPU per current documentation. That is a reference milestone, not a universal optimum for every API.

Illustrative example:

| Memory | Duration | Approximate Compute |
|---:|---:|---:|
| 512 MB | 400 ms | 0.20 GB-s |
| 1,024 MB | 230 ms | 0.23 GB-s |
| 1,769 MB | 120 ms | 0.21 GB-s |
| 3,072 MB | 90 ms | 0.27 GB-s |

Figures are hypothetical for illustration. Higher memory can cut duration while increasing total compute cost. Benchmark against your actual workload rather than picking the smallest MB setting.

## 16. Tuning Java Handlers and Frameworks

Items to inspect:

- Decouple handlers from domain logic for independent testing.
- Shrink package size and include only needed dependencies.
- Initialize AWS SDK clients outside the handler.
- Reuse HTTP clients and bounded connection pools.
- Minimize unnecessary reflection and classpath scanning.
- Avoid allocating large objects or repeatedly serializing on hot paths.
- Avoid sequential blocking calls when queries can be combined safely.
- Avoid sizing thread pools larger than CPU or downstream capacity.
- Never hold mutable request data in static fields.
- Monitor GC pauses, heap usage, and allocation rates during stress tests.

If your API uses Spring Boot, Quarkus, Micronaut, or another framework, benchmark your actual application. Never infer startup times or memory footprints solely from generic framework benchmarks.

## 17. Reusing HTTP Clients and SDKs

Opening new connections on every request raises latency and CPU usage, especially as Java functions scale across many execution environments.

Best practices:

- Initialize shared SDK clients and HTTP clients during initialization.
- Enable appropriate connection reuse and keep-alive.
- Cap connection pool size according to concurrency and downstream limits.
- Set connect timeouts, response timeouts, and idle timeouts.
- Detect stale connections and reconnect cleanly.
- Never let request-specific headers or credentials persist across invocations.
- Never allow pools to open unbounded connections.

Execution environments may be reused, but they are not guaranteed to live forever. Lambda may freeze or close idle connections; code must handle connection resets and reconnect gracefully.

## 18. Databases as a Common Bottleneck in Serverless APIs

Lambda can scale faster than a database can accept new connections. If each environment opens several connections, a burst can exhaust database connections even while Lambda CPU remains low.

Calculate maximum potential connections:

\[
PotentialConnections =
LambdaConcurrency \times PoolSizePerEnvironment
\]

For example, 80 environments each holding a pool of 5 connections:

\[
80 \times 5 = 400\text{ connections}
\]

This is the potential ceiling, not always opened simultaneously. Still, compare it against the database's `max_connections` minus capacity reserved for other apps, migrations, monitoring, and administration.

Mitigations:

- Cap Lambda Reserved Concurrency to match database capacity.
- Reduce per-environment pool sizes.
- Reuse connections.
- Use efficient queries and proper indexes.
- Eliminate N+1 queries.
- Apply pagination and bound result sets.
- Use RDS Proxy when workloads open many short-lived connections and benefit from pooling/multiplexing.
- Consider DynamoDB or another datastore suited to the access pattern when relational queries are unnecessary.

RDS Proxy helps manage and pool connections between clients and the database. It does not make expensive queries run faster, nor does it replace concurrency caps, SQL optimization, or proper indexing.

## 19. Tuning RDS Proxy and Connection Pools

Monitor:

- `DatabaseConnections`.
- `MaxDatabaseConnectionsAllowed`.
- `DatabaseConnectionsBorrowLatency`.
- Connection borrow timeouts.
- Query latency and database CPU.
- Connection pinning if the proxy cannot multiplex sessions.

If borrow latency climbs, the proxy may be nearing available connection limits or queries are holding connections too long. Enlarging the client pool will not fix this and often makes contention worse.

RDS Proxy incurs its own cost. Weigh proxy cost against reduced connection churn, fewer connection errors, and stronger burst tolerance.

## 20. Configuring Tiered Timeouts

Timeouts must be ordered cleanly so lower tiers do not continue hanging after callers have already given up.

Example hierarchy:

~~~text
Client timeout:            8 seconds
API Gateway integration:   7 seconds
Lambda timeout:            6 seconds
Database query timeout:    3 seconds
External API timeout:      2 seconds
~~~

These numbers are illustrative. In practice, the sum of sequential dependency times plus processing overhead must fit inside Lambda and gateway timeouts.

When calling multiple dependencies in parallel, budget for the slowest branch plus overhead. When calling sequentially, sum each step's budget. Leave margin for response serialization and cleanup.

Never let retries across multiple layers multiply unexpectedly. For instance, 3 client retries × 2 gateway retries × 3 SDK retries can amplify traffic far beyond baseline load. Retry only transient errors, use exponential backoff with jitter, and ensure operations are idempotent.

## 21. Rate Limiting and Downstream Protection

Rate limits shield APIs and dependencies from traffic bursts. Enforce limits by route, API key, tenant, or client identity.

Principles:

- Cap sensitive write routes lower than read routes if dependencies require protection.
- Return `429` with `Retry-After` per the API contract.
- Clients retry with backoff and jitter.
- Never retry indefinitely.
- Cap concurrency at the function level.
- Apply bulkheads per dependency.
- Add circuit breakers for partner APIs.
- Return degraded responses when business rules permit.
- Offload long-running work to queues and return `202 Accepted`.

Never treat API Gateway throttling as the sole protection for the database. Lambda concurrency, application semaphores, connection pools, and database capacity must be aligned together.

## 22. Optimizing Payloads, Serialization, and Pagination

Large payloads inflate network time, memory consumption, and serialization cost. Mitigations:

- Return only fields clients actually need.
- Enforce pagination and maximum page sizes.
- Never serialize entire entity graphs.
- Use dedicated response DTOs.
- Avoid serializing objects with lazy-loaded relationships.
- Compress responses when clients and gateways support it and bandwidth savings outweigh CPU cost.
- Enforce request size limits.
- Use object storage for large files instead of streaming them through API functions.
- Avoid logging full request/response bodies.

If a response requires hundreds of thousands of records, synchronous APIs are unsuitable. Use an async export job, write results to object storage, and return a time-limited URL.

## 23. Caching and Read-Heavy Workloads

Caching reduces database queries and latency for infrequently changing data.

Caching layers may include:

- Client caching with `Cache-Control`/`ETag`.
- CDN or edge caches.
- API Gateway caching when using REST APIs with supported configurations.
- In-process application caches inside the execution environment.
- Shared Redis/ElastiCache or managed cache services.

Define explicitly:

- TTL.
- Cache keys and tenant isolation.
- Invalidation when data changes.
- Fallback behavior when the cache is unavailable.
- Cache stampede protection and single-flight coalescing.
- Safeguards preventing sensitive data from leaking across tenants.
- Cache hit ratio and cost impact.

Never treat Lambda in-memory caches as the authoritative data source. Environments recycle frequently and separate instances maintain independent caches.

## 24. Designing Observability Before Load Testing

Without dashboards, a load test only tells you clients observed slowness—not which layer caused it.

Cover three observability layers:

**API Gateway**
- Count.
- 4xx and 5xx.
- Latency.
- IntegrationLatency.
- DataProcessed.
- Throttling and route-level metrics if enabled.

**Lambda**
- Invocations.
- Errors.
- Throttles.
- Duration.
- ConcurrentExecutions.
- ProvisionedConcurrencyUtilization and Spillover if using PC.
- Init Duration from logs/traces.
- Max Memory Used from REPORT logs.

**Database / Dependencies**
- CPU, memory, and connections.
- Query latency.
- Lock waits.
- Connection borrow latency.
- Cache hits/misses.
- Partner API latency and 429/5xx rates.
- Network errors and timeouts.

API Gateway HTTP APIs emit default metrics at one-minute granularity. Detailed route metrics can incur extra CloudWatch costs; enable them when diagnosing specific routes.

## 25. Tracing and Correlation IDs

Propagate a single request/correlation ID end to end:

~~~text
Client
  -> API Gateway request ID
  -> Lambda context request ID
  -> Application correlation ID
  -> Database query / external API
  -> Response
~~~

Logs should include:

- Timestamp.
- Correlation ID.
- Lambda request ID.
- Route and HTTP method.
- Status code.
- Application duration.
- Dependency duration.
- Retry count.
- Release/version identifier.
- Error code.

Use AWS X-Ray or OpenTelemetry to trace critical spans. Never log access tokens, passwords, secrets, authorization headers, or raw PII.

If tracing adds measurable overhead, apply sensible sampling and re-measure afterward. Avoid leaving 100% tracing enabled permanently if it hurts cost or throughput without clear justification.

## 26. Diagnosing Bottlenecks from Metrics

| Symptom | Likely Cause | Next Investigation |
|---|---|---|
| API `Latency` rises while `IntegrationLatency` stays flat | Gateway/auth/edge/client path | Authorizers, WAF, TLS, DNS, and client network |
| `IntegrationLatency` rises alongside Lambda `Duration` | Function or dependencies | Lambda logs, traces, and downstream spans |
| Lambda `Duration` climbs with memory near limit | Memory pressure, GC, or large payloads | Max Memory Used, heap, and GC behavior |
| `Throttles` increase | Lambda concurrency or scaling/quotas | `ConcurrentExecutions`, reserved/account quotas |
| API Gateway 429 increases | Gateway throttle target or quota | Route/account limits and client rates |
| Lambda 5xx climbs with high database CPU | Query or database bottleneck | Query plans, locks, and connections |
| Database borrow latency rises | Proxy/pool near exhaustion | RDS Proxy metrics and pool settings |
| p99 spikes while p50 stays steady | Cold starts or outlier dependencies | Init Duration, traces, and slow queries |
| Errors grow over long runs | Leaks, pool exhaustion, memory growth | Soak tests, heap, connections, and threads |
| Throughput stalls despite adding VUs | Generator, quota, or saturated downstream | Generator CPU, dropped iterations, throttles |
| Cost grows faster than traffic | Retries, duration, logging, or dependencies | Cost per success and per-component breakdown |

Never tune parameters before diagnosing the bottleneck. Raising memory when the database is saturated only increases Lambda cost without improving throughput.

## 27. One-Variable-at-a-Time Tuning Process

A controlled optimization loop:

1. Run a baseline with the current configuration.
2. Record the artifact, environment, payload, and test profile.
3. Identify the primary bottleneck.
4. Pick a single variable to change.
5. Rerun the exact same workload.
6. Compare latency, throughput, errors, resource usage, and cost.
7. Run correctness regression tests.
8. Keep the change if SLOs and unit costs improve.
9. Otherwise roll back the change and document why.
10. Repeat with the next variable.

Never change memory, timeouts, reserved concurrency, pool sizes, and route throttles simultaneously. If results improve, you will not know which change caused the gain.

## 28. Configuration Matrix to Benchmark

| Variable | Candidate Values | Deciding Metrics |
|---|---|---|
| Lambda memory | 512 / 1,024 / 1,769 / 3,072 MB | Duration, GB-seconds, peak memory |
| Lambda timeout | Aligned with latency budget and tail duration | Timeout rate, duration |
| Reserved concurrency | Sized to dependency capacity | Throttles, DB connections |
| Provisioned Concurrency | Forecasted baseline/peak | Init, spillover, utilization, cost |
| Java framework | Current framework/config vs. lean setup | Init Duration, memory, package size |
| HTTP connection pool | Small / medium / large bounded sizes | Pool wait times, connection errors |
| DB pool | Sized to concurrency and DB max connections | DB CPU, borrow latency |
| API Gateway throttle | Per-route rate/burst | 429s, downstream saturation |
| Cache TTL | Per freshness requirements | Hit ratio, stale responses, DB load |
| Payload/page size | Small / medium / large | Serialization, network, memory |

Values here are illustrative benchmark ranges. Never roll out new settings without checking service and dependency limits first.

## 29. Example Lambda Configuration Updates

Updating memory and timeout:

~~~bash
aws lambda update-function-configuration \
  --function-name orders-api \
  --memory-size 1769 \
  --timeout 10
~~~

Setting Reserved Concurrency:

~~~bash
aws lambda put-function-concurrency \
  --function-name orders-api \
  --reserved-concurrent-executions 80
~~~

These commands are illustrative. Replace function names and values with benchmarked settings, verify account quotas, and obtain change approvals before applying to production.

When using aliases/versions, ensure API Gateway integrations target the intended version/alias and follow publish/rollback procedures. Never assume updating `$LATEST` propagates uniformly to every caller.

## 30. Defining the Capacity Envelope

After testing, document the proven boundaries:

| Component | Deliverable Evidence |
|---|---|
| API | Sustained RPS, burst RPS, p95/p99 |
| Lambda | Memory, timeout, peak concurrency, throttles |
| API Gateway | Route/account throttle settings, 429 behavior |
| Database | Connection limits, tested query throughput, CPU headroom |
| Cache | Hit ratio, throughput, and memory usage |
| External APIs | Rate limits, timeouts, retry policies |
| Load generator | Worker/VU count, CPU/network utilization |
| Cost | Cost per 1,000 requests and per successful transaction |

A capacity envelope applies only to the exact recorded artifact, configuration, Region, dataset, dependencies, and test profile. Whenever frameworks, schemas, queries, memory, routes, or database classes change, re-evaluate it.

## 31. Calculating Cost per Successful Request

Serverless API costs can include:

- API Gateway requests and data processing.
- Lambda requests and GB-seconds.
- Provisioned Concurrency if enabled.
- CloudWatch Logs, metrics, and tracing.
- Data transfer, NAT, and VPC networking.
- RDS/RDS Proxy, caches, and storage.
- External APIs or downstream services.
- Retries, duplicates, and failed requests.

Simple formulas:

\[
CostPerSuccess =
\frac{TotalTestCost}{SuccessfulBusinessTransactions}
\]

And:

\[
CostPer1000Success =
CostPerSuccess \times 1000
\]

Do not divide by total invocations when a transaction can retry multiple times. Use completed, valid business transactions as the denominator.

Separate load-test costs from steady-state production costs. Load tests generate synthetic traffic, logs, and traces; track them separately so they do not skew production cost forecasts.

## 32. Pre-Production Release Gate

Before opening production traffic, verify:

**Correctness**
- Contracts and response schemas are accurate.
- Authentication/authorization behave properly.
- Validation and error mappings are accurate.
- Write operations enforce idempotency.
- Pagination and data consistency hold.

**Performance**
- Sustained and peak loads meet SLOs.
- p95/p99 meet targets.
- Error rate stays within error budget.
- Zero unexplained dropped iterations.
- Databases and external APIs retain headroom.

**Reliability**
- Timeouts and retries are bounded.
- Throttling returns the expected status codes.
- Circuit breakers and backpressure work.
- Alarms and dashboards are active.
- Rollbacks have been rehearsed.

**Security**
- IAM follows least privilege.
- Secrets reside in secret stores.
- Logs exclude tokens and PII.
- Rate limits and abuse protections are active.
- Test data is cleaned up per policy.

**Cost**
- Cost per successful transaction fits within budget.
- Logging/tracing volume is bounded.
- Provisioned capacity is justified and scheduled if needed.
- Cost anomaly and budget alerts have owners.

## 33. Canary and Rollout After Load Testing

Passing load tests does not mean shifting 100% of traffic immediately. Roll out in stages:

~~~text
Stage 1: 1% traffic
Stage 2: 5% traffic
Stage 3: 10% traffic
Stage 4: 25% traffic
Stage 5: 50% traffic
Stage 6: 100% traffic
~~~

Hold each stage long enough to observe meaningful signals. Monitor p95/p99, 4xx/5xx, Lambda Throttles, database connections, business success, and cost.

Use aliases, weighted routing, or appropriate deployment mechanisms. Define rollback thresholds before starting. If error rates or business invariants breach thresholds, halt traffic expansion and revert to the stable version.

## 34. Preparing Operational Handover

Handover is more than sharing source code and an endpoint URL. The operations team must understand how the system works, its load limits, how to handle failures, and how to recover.

The handover package should contain:

| Area | Contents |
|---|---|
| Service overview | API purpose, owners, dependencies, and architecture diagram |
| API contract | OpenAPI, routes, request/response schemas, error codes |
| Authentication | Auth flows, roles, scopes, token lifetimes, and secret references |
| Deployment | IaC, artifacts, runtime, versions/aliases, and release process |
| Configuration | Memory, timeouts, concurrency, throttles, environment variable names |
| Networking | VPCs, subnets, security groups, endpoints, and DNS |
| Data | Database schemas, migrations, indexes, backups, and retention |
| Observability | Dashboards, alarms, log groups, traces, and correlation IDs |
| Capacity | Tested RPS, p95/p99, concurrency, dependency limits |
| Cost | Monthly forecast, cost per transaction, and budget alarms |
| Operations | Runbooks, on-call owners, escalation, and incident processes |
| Recovery | Rollbacks, backup restores, and DR assumptions |
| Security | IAM policies, secret locations, data classification, and audits |

Never include raw secret values or private keys in handover documentation. Document only secret names, ARNs/references, and access request procedures.

## 35. Dashboards and Alarms to Hand Over

Minimum dashboards should include:

**API Gateway**
- Request count.
- 4xx/5xx.
- Latency and IntegrationLatency.
- Throttles/429s.

**Lambda**
- Invocations, Errors, Throttles.
- Duration p50/p95/p99.
- ConcurrentExecutions.
- Init Duration from logs/traces.
- Max Memory Used from REPORT logs or Lambda Insights.
- Provisioned Concurrency utilization/spillover if enabled.

**Database**
- CPU/memory.
- Connections.
- Query latency.
- Lock waits.
- Proxy borrow latency if using RDS Proxy.

**Business**
- Orders created/confirmed.
- Payment successes/failures.
- Validation rejections.
- Duplicate/idempotency conflicts.
- Business transaction success rate.

Alarms must specify owners, severities, thresholds, evaluation windows, and actions to take when triggered. Avoid creating alarms purely to turn a dashboard green; every alarm should link to a concrete runbook or decision.

## 36. API Incident Runbook

A concise runbook should guide responders:

| Symptom | First Action |
|---|---|
| HTTP 429 spiking | Check Gateway throttles, Lambda concurrency, and client retries |
| HTTP 5xx spiking | Separate Lambda errors, integration errors, and dependency failures |
| p99 climbing | Inspect Init Duration, database latency, and external APIs |
| Lambda Throttles rising | Check account quotas, reserved concurrency, and scaling |
| High database connections | Inspect pools, Lambda concurrency, and RDS Proxy |
| Memory near limit | Inspect heap, payloads, allocations, and GC |
| Abnormal cost spike | Inspect request volume, retry loops, logs, and recursive invocations |
| API unreachable | Check DNS, custom domains, API deployments, IAM/resource policies |
| Faulty new release | Halt rollout and roll back alias/version |
| Data inconsistency | Halt risky side effects, reconcile data, and execute recovery steps |

Runbooks must name exact dashboards, log queries, accountable owners, and escalation criteria. Never expect on-call engineers to hunt through source code for basic operational details.

## 37. Essential Contents of a Load Test Report

The final report should preserve:

- Date, time, and Region.
- Git commit, artifact digest, and Lambda version.
- API stage, routes, and Gateway configuration.
- Memory, timeout, concurrency, and database configuration.
- Load generator, worker/VU counts, and script version.
- Test data profile and route mix.
- Phases executed: smoke, baseline, load, spike, soak, recovery.
- Actual RPS and dropped iterations.
- p50/p95/p99 latency.
- 4xx/5xx, throttles, and timeouts.
- Lambda Duration, memory, and concurrency.
- Database CPU, connections, and query latency.
- Cost estimates and cost per success.
- Limits encountered.
- Conditions not yet covered by testing.
- Final configuration decisions and approvers.

Do not share only dashboard screenshots. Preserve raw results, scripts, and metadata so tests can be reproduced under identical conditions.

## 38. Common Load Testing Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Testing only the handler directly | Misses Gateway and auth overhead | Test end-to-end |
| Using closed workloads for RPS targets | Slow server throttles generator emission | Use arrival-rate models |
| Under-provisioned load generators | Creates false bottlenecks | Monitor generator CPU, network, and dropped iterations |
| Testing only one route | Misses heavy routes | Use realistic workload mixes |
| Using a single test record | Caches/hot keys distort results | Distribute realistic test data |
| Skipping quota checks | Tests fail due to account limits | Preflight Service Quotas |
| Non-idempotent retries | Creates duplicate orders/payments | Use idempotency keys |
| Uncontrolled soak tests | Runaway cost and data buildup | Set budgets, duration caps, and cleanup |
| Raising Lambda concurrency too fast | Exhausts database connections | Align concurrency and pool sizes |
| Picking lowest memory blindly | CPU-bound functions run slower | Benchmark memory/CPU trade-offs |
| Looking only at average latency | Hides tail latency issues | Measure p95/p99 |
| No rollback plan | Faulty releases prolong outages | Maintain runbooks and canary gates |

## 39. API Service Handover Checklist

**Architecture and Contract**

1. Are request path and dependency diagrams up to date?
2. Have OpenAPI specs and the error contract been handed over?
3. Are authentication, authorization, and rate limits documented?
4. Are idempotency and pagination semantics explained?

**Performance and Capacity**

5. Is the load test report reproducible?
6. Does the capacity envelope state RPS, concurrency, and p95/p99?
7. Are Lambda memory, timeout, and concurrency documented?
8. Are Gateway quotas and throttles verified?
9. Are database connection/pool limits documented?
10. Has cost per successful transaction been calculated?

**Operations**

11. Do dashboards and alarms have assigned owners?
12. Do runbooks cover 429, 5xx, timeouts, and database failures?
13. Has version/alias rollback been rehearsed?
14. Are on-call rotations and escalation paths defined?
15. Are backup/restore procedures and DR assumptions documented?

**Security and Access**

16. Has least-privilege IAM been reviewed?
17. Have secret references and rotation owners been handed over?
18. Are logs scrubbed of tokens and PII?
19. Is load-test data cleaned up or governed by retention?
20. Do the right teams have console, log, and dashboard access?

**Acceptance**

21. Has the service owner received source code, artifacts, and IaC?
22. Has the operations owner approved dashboards and runbooks?
23. Are SLOs and error budgets agreed upon?
24. Are known limitations and residual risks documented?
25. Is there a signed handover record and support start date?

## References

- [AWS Lambda: How to test serverless functions and applications](https://docs.aws.amazon.com/lambda/latest/dg/testing-guide.html)
- [AWS Lambda: Understanding concurrency and scaling](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [AWS Lambda: Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)
- [AWS Lambda: Best practices for Lambda Event Functions](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [AWS Lambda: Java handler and code best practices](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html)
- [Amazon API Gateway: HTTP API CloudWatch metrics](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-metrics.html)
- [Amazon API Gateway: HTTP API throttling](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html)
- [Amazon RDS: Using Lambda with RDS](https://docs.aws.amazon.com/lambda/latest/dg/services-rds.html)
- [Amazon RDS Proxy: Connection considerations](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-connections.html)
- [Grafana k6: Constant arrival rate executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/)

## Conclusion

Load testing a Java serverless API must exercise the full request path using a representative workload. Distinguish RPS, concurrency, Gateway throttling, and downstream limits; measure p95/p99 latency, error rates, memory, duration, database connections, and cost per successful business transaction.

Tune based on evidence, changing one variable at a time and retesting under the same profile. Java handlers should reuse clients safely and minimize initialization and package overhead, while concurrency must match database and external API capacity. Enable Provisioned Concurrency only when startup latency genuinely threatens SLOs.

Handover is complete when the receiving team has clear API contracts, artifacts/IaC, configurations, a capacity envelope, dashboards, alarms, runbooks, rollback procedures, a cost model, and named owners. Load test reports must record both proven limits and untested conditions so benchmark numbers are never mistaken for absolute guarantees across all future traffic.

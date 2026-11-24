# Boundaries Between Functional Testing, Load Testing, and Controlled Fault Experiments

A Spring Boot endpoint returning HTTP `200` across 15 test cases means it **passed the verified functional scenarios**. That result **does not prove** the endpoint holds p95 latency under 500 ms at 100 requests/second, nor does it prove the app recovers after a downstream disconnects, a database fails over, or a pod is killed. Conversely, a load test with a great p95 can still return corrupt data, record duplicate orders, or silently serve wrong fallbacks. Deliberately severing a network link while the system “stays up” also does not prove API contracts, data integrity, and performance targets all hold.

This Knowledge lesson **“Boundaries Between Functional Testing, Load Testing, and Controlled Fault Experiments”** sits in the **Contracts and Resilience** section of the **Spring Boot – testing** module. We design each method around *the question to answer*, *the system layer observed*, *controlled inputs/load/faults*, and *sufficient evidence to conclude*. Examples use **Java 17+, Spring Boot 3.5.16, Spring Framework 6.2.x, JUnit Jupiter 5, Mockito, MockMvc, `@RestClientTest`, `MockRestServiceServer`, and `@SpringBootTest(RANDOM_PORT)`**; **k6** load scripts and **WireMock/Testcontainers Toxiproxy** network fault experiments are separated into standalone activities with safeguards.

**Core rule:** *Functional tests prove a concrete contract under chosen preconditions; load tests measure behavior distributions under concurrency and finite resources; fault/chaos experiments test fault tolerance and recovery under an actively injected failure.* No single method replaces the other two. Never call a `@Test` containing `Thread.sleep` a load test, and never call a mocked `503` response a chaos test on real infrastructure.

## 1. Learning objectives

- Distinguish **functional, contract, integration, performance/load, stress, soak, fault injection, chaos, and disaster recovery tests**.
- Describe **preconditions, stimuli, observations, and postconditions** for each test type.
- Know when to assert exact status/JSON vs. p95/p99/error-rate/throughput distributions vs. recovery times.
- Define SLIs/SLOs and quality thresholds without mistaking a sample lab number for a production SLA commitment.
- Design **healthy baselines**, **degradation curves**, and **recovery paths** to avoid false conclusions.
- Understand differences among `@WebMvcTest`, `@RestClientTest`, `@SpringBootTest(MOCK)`, and `RANDOM_PORT`.
- Deterministically simulate downstream `503`/connection failures to verify retries/fallbacks without waiting on real networks.
- Write a Java service with bounded retries that avoids retrying unrecoverable contract errors and emits clear degraded states.
- Verify fallback responses are never counted as healthy business successes in metrics.
- Understand closed models (VUs) vs. open models (arrival rates) in load generators.
- Interpret k6 `checks`, `thresholds`, p95, and `dropped_iterations` accurately.
- Design latency, connection-reset, and network-partition experiments with WireMock or Toxiproxy in isolated environments.
- Define blast-radius limits, rollbacks, durations, abort criteria, and approvals before injecting faults.
- Recognize retry amplification, retry storms, overload, queue backlogs, thread-pool exhaustion, circuit breakers, and bulkheads.
- Present evidence-backed findings, separating **actually executed runs** from **illustrative samples or expected outcomes**.

## 2. Three different questions

| Method | Primary question | Observed outcome | Example |
|---|---|---|---|
| **Functional testing** | “Given specific inputs and state, does the system obey the contract?” | Status, JSON, headers, data, side effects, call counts | Downstream 503 twice → `UNKNOWN`/degraded response, exact attempts |
| **Load testing** | “Under a defined workload over time, what are service quality and resource usage?” | Throughput, latency distribution, error ratio, saturation, queues, GC, drops | 10 RPS for 30 s in isolated environment; p95 and business success rate |
| **Controlled fault injection** | “When component X slows/fails/disconnects, how does the system detect, contain, and recover?” | Degraded behavior, detection, retry/CB/bulkhead, recovery time, data integrity | Inject 1.2 s latency on test link, remove toxic, verify recovery |

Methods can combine—for example, **running a small workload while cutting a downstream link**. Whenever combining them, specify both the *workload* and the *injected fault*. A single-request test does not prove load capacity; a fault-free load test does not prove recovery; a chaos test returning 200 while losing data also fails.

### 2.1. A pragmatic definition of “boundary”

A test boundary is **what the test has the authority to claim**, not a class name or framework annotation:

- `MockMvc`: verifies Spring MVC routing/controllers/filters inside a mock servlet; **uses no real TCP**.
- `MockRestServiceServer`: intercepts outbound `RestClient`/`RestTemplate` at the request factory; asserts URL/status/headers; **does not simulate real sockets, TLS, or redirects**.
- `@SpringBootTest(RANDOM_PORT)`: starts a real HTTP server so clients connect over local TCP; yet if downstream is mocked with Mockito, **downstream networking remains untested**.
- k6 hitting the live app: measures end-to-end results from the load generator, yet if the backend data source is a fake/mock, conclusions apply only to that stubbed topology.
- Toxiproxy in front of a downstream: affects TCP connections routed through the proxy; does not verify DNS, control planes, or connections bypassing the proxy.

## 3. Functional contracts cover more than HTTP status

An API contract must specify at least:

1. **Preconditions:** principals, seed data, service dependencies, configs, and feature flags.
2. **Inputs:** method/path/query/headers/body and validation.
3. **Outputs:** HTTP status, schema, per-field semantics, headers, and error codes.
4. **Side effects:** DB writes, outbox events, emails, idempotency keys.
5. **Failure behavior:** timeouts, 503, malformed responses, exhausted retries, fallbacks.
6. **Observability:** correlation IDs, traces, degraded markers, and key metrics.

For example, an inventory check API returns:

```json
{
  "sku": "BOOK",
  "status": "AVAILABLE",
  "source": "REMOTE",
  "degraded": false
}
```

When downstream fails, it may return:

```json
{
  "sku": "BOOK",
  "status": "UNKNOWN",
  "source": "FALLBACK",
  "degraded": true
}
```

In this demo, both use HTTP `200` because the public contract allows reporting “unknown” rather than falsely claiming “out of stock”. **Yet the two responses do not share equal business quality.** If a load test evaluates only `http_req_failed` by HTTP status, degraded 200s look like HTTP successes. Track a **business-level SLI** counting `degraded:true` and validating fields. Another product may legitimately choose HTTP `503` when stock is unknown; what matters is aligning the contract and SLI, not forcing one status everywhere.

## 4. Functional testing: determinism and expressiveness

Functional tests specify **clear inputs and expected outputs**. Example:

```text
Given sku=BOOK and downstream returns AVAILABLE
When GET /api/availability/BOOK
Then HTTP 200, sku=BOOK, status=AVAILABLE,
     source=REMOTE, degraded=false

Given downstream returns 503 first, then 200
When GET /api/availability/BOOK
Then exactly 2 gateway calls, status=AVAILABLE,
     no fallback used

Given downstream returns 503 twice
When GET /api/availability/BOOK
Then status=UNKNOWN, degraded=true,
     attempts capped at 2

Given downstream returns sku=PEN for request BOOK
When GET /api/availability/BOOK
Then 502/contract error, NOT treated as retryable 503
```

These are **functional resilience tests**: they use controlled fault injection to verify error handling in code. They **do not** establish p95, throughput, or survival under real network partitions because they lack concurrency and real infrastructure.

### 4.1. When is it a “contract test”?

Consumer-driven contracts, schema validation, OpenAPI compatibility, or provider state tests verify whether **two sides agree on message structure and semantics**. A WireMock stub only simulates “a provider might return 503”; it does not prove the production provider conforms to the schema or other states. With Pact or Spring Cloud Contract, verify both provider and consumer per system setup.

**Keep both:** contract tests ensure shared communication meaning; resilience tests verify how the consumer reacts when the provider returns one of the contract's allowed outcomes (or breaks it).

## 5. Load testing measures distributions, not single assertions

Performance/load tests generate many operations under a **defined workload**:

- Request rate or virtual user count, and arrival distribution.
- Endpoint mix and read/write ratios.
- Dataset cardinality, cache hit/miss ratios, and SKU distributions.
- Payload sizes, authentication, cookies, and connection reuse.
- Warm-up, steady-state duration, and ramp-up/ramp-down.
- Load generator placement, network latency, and client machine limits.
- Whether backend services and databases mirror the target environment.

Metrics to capture:

| Metric | Meaning | Pitfall |
|---|---|---|
| Throughput/RPS | Completed requests per second | Completing many requests does not mean they were correct |
| Offered arrival rate | Intended request start rate per second | May go unmet due to too few VUs or an overloaded generator |
| p50 | Median latency | Hides tail behavior |
| p95/p99 | 95th/99th percentile latency | Needs sufficient sample size; never extrapolate a one-off run to an annual SLA |
| Error rate | Fraction of failed requests by category | HTTP 200 degraded responses may go uncounted |
| Business-success rate | Fraction of valid, non-degraded business responses | Requires custom checks/metrics |
| Saturation | CPU, thread pools, connection pools, DB pools, queues | Measure on the system under test, not only the client |
| Drops | Iterations the load generator failed to launch | Can distort RPS targets while p95 looks artificially healthy |
| Recovery time | Time from fault removal until SLIs return to baseline | Meaningful only with a baseline and continuous observation |

**Never use `assertTrue(elapsedMillis < 100)` inside a single JUnit test to claim p95 < 100 ms.** Single measurements suffer from JIT, OS scheduling, GC, CI contention, and cold caches. Unit-test timings fit bounded failure semantics, not load characterization.

## 6. SLI, SLO, SLA, and error budgets

- **SLI:** a quantitative measure of a service property, e.g., fraction of valid GETs completing ≤500 ms **and** returning non-degraded results.
- **SLO:** an internal target for an SLI over a window, e.g., 99.9% of requests over a rolling 30-day window succeed as defined.
- **SLA:** an external contractual commitment, typically carrying penalties if breached.
- **Error budget:** allowable unreliability within the SLO window; a chaos experiment consumes error budget if run in production.

Illustrative **lab** target (NOT a production SLA):

```text
Workload: GET /api/availability/BOOK, 10 RPS, 30 s, isolated local app.
Functional: 200, valid schema, matching sku, degraded=false.
HTTP error rate: < 1%.
Business success rate: > 99%.
p95 client HTTP latency: < 500 ms.
dropped_iterations: 0.
No unauthorized data change; no persistent queue growth.
```

Thresholds must derive from product SLO/capacity requirements, never chosen merely to make tests green. And **30 seconds × 10 RPS** is a tiny lab exercise illustrating measurement, **not** proof of a 30-day SLA or production peak capacity.

## 7. Load, stress, spike, soak, and capacity tests differ

| Type | Workload | Question |
|---|---|---|
| Smoke performance | Very small, brief | Is the harness hitting the right app with valid metrics? |
| Baseline | Low, steady load | Latency/errors with near-zero contention |
| Load | Expected sustained traffic | Do we meet SLOs at target load? |
| Stress | Ramped above expected capacity | Where does degradation start, and do backpressure/failures stay graceful? |
| Spike | Sudden surge then drop | How do autoscaling, queues, and connection pools react? |
| Soak/endurance | Moderate load over long duration | Any memory leaks, FD leaks, GC drift, or connection exhaustion? |
| Scalability | Vary replicas/CPU at fixed workload | How do throughput and latency scale? |
| Resilience under load | Steady workload + controlled fault | How do degradation and recovery behave under real pressure? |

**Each type requires its own dataset and acceptance criteria.** This demo's 30-second script is not a soak test. Never aim stress/spike tests at shared staging or production just because a script exists; load can starve CPU, DB connections, and queues for everyone else.

## 8. Open model vs. closed model in k6

**Closed model:** a fixed number of virtual users run loops; a new iteration starts only after the previous finishes. When the server slows down, the request rate **throttles itself**, producing lower throughput while hiding latency blowups.

**Open model:** fixes an arrival rate independent of response time, e.g., `10 iterations/s`. When the service slows down, more concurrent VUs are needed to sustain the pace. Without enough VUs, k6 logs `dropped_iterations`. Open models better match external RPS arrivals, provided the load generator has sufficient capacity.

Example:

```javascript
export const options = {
  scenarios: {
    availability: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 20
    }
  }
};
```

This is a snippet; the full script appears in section 27. With `constant-arrival-rate`, **never add `sleep(1)` at the end of an iteration** to “pace 1 RPS per VU”; the executor schedules arrivals itself. Setting 10 RPS in the script does not guarantee 10 requests/s if iterations drop or if one iteration fires multiple HTTP calls.

## 9. Controlled fault injection does not mean randomly breaking production

A **fault injection test** injects a reproducible fault at a boundary (HTTP 503, timeout, connection reset, Redis unavailable) to observe specific handling. A **chaos experiment** adds a steady-state hypothesis, system-wide scope, bounded blast radius, live measurement, and abort/recovery mechanisms, typically on production-like topologies. Do not use the two terms interchangeably.

Typical tiers:

1. **Unit:** Mockito throws `UpstreamUnavailableException` twice; verifies retry count and fallback.
2. **HTTP stub:** WireMock returns `503` or delays 1.2 s on an endpoint; real client opens a socket to the stub.
3. **Network proxy:** Toxiproxy adds latency/jitter or cuts TCP links between the app and test dependencies.
4. **Platform fault:** Restarts/kills a non-critical pod in a test namespace or blocks egress on one replica by policy.
5. **Production chaos:** Only with **explicit authorization**, system ownership, error budgets, blast-radius/rollback controls, and on-call coverage; **never** a default step in this lesson.

Level 1 verifies exception handling in code. Levels 3–4 reveal connection-pool behavior, autoscaler/backpressure reactions, and real recovery across topologies. Level 5 carries operational risk and requires formal change approval.

## 10. Three phases of a trustworthy fault experiment

```text
A. BEFORE (steady state)
  - Verify baseline functional contracts
  - Measure RPS, p95/p99, errors, business success, saturation
  - Confirm dashboards/traces/logs are live

B. DURING (fault active)
  - Inject only the approved, registered fault within scope
  - Log start time, target, intensity, TTL, and request IDs
  - Measure degraded mode, retries, queues, pools, error budget
  - Abort automatically if abort criteria trigger

C. AFTER (recovery)
  - Remove fault deterministically (finally, TTL, operator rollback)
  - Observe service returning to steady state
  - Verify data integrity, backlog drain, and zero duplicate side effects
  - Archive artifacts: config, timeline, metrics, findings
```

Testing only that the system returns 200 **during** a fault—without checking fallback ratios, data integrity, and recovery **after** clearing the fault—makes calling it “resilient” unwarranted.

## 11. Failure matrix to cover

| Injected fault | Functional expectation | Load/fault observation |
|---|---|---|
| Upstream HTTP `503` | Bounded retries, contract-compliant fallback/503 | Retry amplification, degradation rate |
| Upstream HTTP `404` | No blind retries; domain/error mapping | No retry storms on missing items |
| Connection reset | Timeout, exception mapping, cleanup | Does the connection pool recover? |
| Latency exceeding timeout | Bounded wait, never hang forever | p95/p99, thread exhaustion, backlog |
| DNS failure | No token/secret leaks; bounded failure | DNS caching and recovery |
| TLS error / expired cert | Fail closed, never disable cert checks | Failed request count, accurate alerts |
| Exhausted DB pool | No unbounded thread stalls | Pending connections, RPS collapse |
| Redis unavailable | Explicit cache-miss/fallback policy | How much does DB load surge? |
| Pod restart | In-flight requests follow contract | Readiness/liveness, retries, zero downtime |
| Queue lag | Eventual status and backpressure | Lag drain / recovery duration |
| Rate limit `429` | Honor `Retry-After`/policy | Throttling / retry storms |
| Invalid downstream JSON | 502/contract failure, no silent falsehoods | Bad-contract counts |
| Clock/time skew | Expiry/lease/idempotency holds | Split-brain / duplicate processing |

Never inject every fault at once and lose track of which caused which symptom. Start with **one fault, one hypothesis, one primary metric**, then layer complexity intentionally.

## 12. Spring Boot test annotations: what do they prove?

| Tool/annotation | Good for | Does not prove |
|---|---|---|
| Plain JUnit/Mockito | Domain policies, retry counts, unit idempotency | HTTP sockets, TLS, capacity |
| `@WebMvcTest` + `MockMvc` | Routing, schemas, statuses, headers, validation | Network stack or real load |
| `@RestClientTest` + `MockRestServiceServer` | Outbound URL/headers/status mapping, 503 stub | Real TCP timeouts or connection resets |
| `@SpringBootTest` (default MOCK) | App context, bean wiring, MockMvc if enabled | Embedded server socket |
| `@SpringBootTest(RANDOM_PORT)` | Real inbound TCP + servlet filters | Real downstream if still mocked |
| WireMock/MockWebServer | Real stub HTTP socket, delays/resets/retries | True production downstream capacity |
| Testcontainers/Toxiproxy | Containerized/service networking with faults | Production networks, cloud control planes |
| k6/Gatling | Load generation per workload profile, aggregate metrics | Business correctness if checks are weak |
| Chaos platform/cluster experiments | Failure behavior and topology recovery | Every API contract or data edge case |

**`RANDOM_PORT`** opens a real server and port; clients speak HTTP over TCP. **MockMvc** never opens TCP, even inside `@SpringBootTest`. Whenever an HTTP client is replaced by a Mockito bean in a full-context test, document that boundary explicitly.

## 13. Runnable demo: contract of the inventory check service

The sample app provides:

- `GET /api/availability/{sku}`.
- SKUs allow only uppercase letters, digits, and hyphens; length 1–24.
- Calls downstream `GET {demo.stock.base-url}/stock/{sku}`.
- Downstream JSON returns `sku` and `stock` in `{AVAILABLE, OUT_OF_STOCK}`.
- When downstream returns 503 or a connection I/O failure, retry up to **2 attempts**, then return `UNKNOWN` + `degraded=true`.
- When downstream returns JSON with a mismatched SKU or invalid stock status, **fail closed** with `502`, never treating it as transient 503.
- When the caller supplies a malformed SKU, return `400` before calling the gateway.
- On success, return JSON with `source=REMOTE, degraded=false`.
- On fallback, return JSON with `source=FALLBACK, degraded=true`; HTTP 200 is strictly a demo contract choice.
- No DB, transactions, or payment/order side effects; the demo intentionally uses an idempotent GET.

**Operational note:** The code retries twice **immediately with no backoff** to keep JUnit tests deterministic. This is an **illustrative mechanism**, not a production retry policy. Real systems require overall timeouts, exponential backoff/jitter, retry budgets, circuit breakers, idempotency, and retry-amplification monitoring; never copy a bare retry loop into high-load services.

## 14. Demo diagram and test paths

```text
GET /api/availability/BOOK
     |
     v
InventoryController
     |
     v
InventoryService
  - validate sku
  - call gateway at most twice on transient failure
  - AVAILABLE / OUT_OF_STOCK / UNKNOWN
     |
     v
StockGateway (interface)
     |
     +-- HttpStockGateway (RestClient) ---> GET /stock/BOOK
     |                                  -> backend or stub
     +-- Mockito fake in service tests
     
Test paths:
1) Unit JUnit: InventoryService + mocked StockGateway
2) @RestClientTest: HttpStockGateway + MockRestServiceServer
3) @WebMvcTest: InventoryController + mocked InventoryService
4) @SpringBootTest RANDOM_PORT: real inbound HTTP + mocked gateway
5) k6 (separate): real app + configured isolated downstream
6) WireMock/Toxiproxy (separate): real outbound network fault
```

Each test path has one vantage point. Never add 1+2+3+4 together and claim “measured performance under network partition”. Paths 5 and 6 must be executed, measured, and archived separately.

## 15. Project source layout

```text
functional-load-fault-boundaries/
  settings.gradle
  build.gradle
  src/main/java/com/example/testboundary/
    TestBoundaryApplication.java
    RemoteStock.java
    InventoryResponse.java
    StockGateway.java
    UpstreamUnavailableException.java
    UpstreamContractException.java
    InvalidSkuException.java
    HttpStockGateway.java
    InventoryService.java
    InventoryController.java
    InventoryErrorAdvice.java
  src/test/java/com/example/testboundary/
    InventoryServiceTest.java
    HttpStockGatewayTest.java
    InventoryControllerTest.java
    InventoryHttpIntegrationTest.java
  load/
    availability.js
```

**Runnable scope:** `src/main`, `src/test`, and Gradle form a project compiling and testing on Java 17 and Spring Boot 3.5.x. k6 requires the standalone `k6` binary and a **running isolated downstream stub/environment** to measure real business success. `load/availability.js` is not a JUnit test and is not executed by `./gradlew test`.

## 16. Gradle files

**`settings.gradle`**

```groovy
rootProject.name = 'functional-load-fault-boundaries'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` provides MVC/RestClient/Jackson; `spring-boot-starter-test` provides JUnit Jupiter, Mockito, MockMvc, and `MockRestServiceServer`. Actuator adds Micrometer/observability foundations without exposing every endpoint publicly by default. k6, WireMock, and Toxiproxy are omitted from Gradle because k6 is external and core tests use Spring's mock server. When extending with network-fault integration, add test dependencies/Docker steps intentionally per sections 30–31.

## 17. Application and DTOs

**`src/main/java/com/example/testboundary/TestBoundaryApplication.java`**

```java
package com.example.testboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                TestBoundaryApplication.class, args);
    }
}
```

**`src/main/java/com/example/testboundary/RemoteStock.java`**

```java
package com.example.testboundary;

public record RemoteStock(
        String sku,
        String stock) {
}
```

**`src/main/java/com/example/testboundary/InventoryResponse.java`**

```java
package com.example.testboundary;

public record InventoryResponse(
        String sku,
        String status,
        String source,
        boolean degraded) {
}
```

These DTOs define clear JSON contracts. `status=UNKNOWN` means **no evidence confirming stock**; it does **not** mean `OUT_OF_STOCK`. Frontends may show “stock unconfirmed” or block checkout per policy. The load test checks this explicitly: HTTP 200 with `degraded=true` does not count as business healthy.

## 18. Port and exception types: separating transient from contract failures

**`src/main/java/com/example/testboundary/StockGateway.java`**

```java
package com.example.testboundary;

public interface StockGateway {
    RemoteStock fetch(String sku);
}
```

**`src/main/java/com/example/testboundary/UpstreamUnavailableException.java`**

```java
package com.example.testboundary;

public class UpstreamUnavailableException
        extends RuntimeException {

    public UpstreamUnavailableException(String message) {
        super(message);
    }

    public UpstreamUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

**`src/main/java/com/example/testboundary/UpstreamContractException.java`**

```java
package com.example.testboundary;

public class UpstreamContractException
        extends RuntimeException {

    public UpstreamContractException(String message) {
        super(message);
    }
}
```

**`src/main/java/com/example/testboundary/InvalidSkuException.java`**

```java
package com.example.testboundary;

public class InvalidSkuException
        extends RuntimeException {

    public InvalidSkuException() {
        super("Invalid SKU");
    }
}
```

**Why separate errors?** Retrying `IOException`/503 makes sense for transient errors, whereas invalid payloads, 401/403 auth errors, or domain 404s will not heal on immediate retry. Wrapping everything in `catch(Exception ex)` and returning a fallback masks programming bugs and breaks contracts. The sample treats only **503** and **`ResourceAccessException`** as unavailable; other statuses become downstream contract failures for clarity, whereas real apps refine policies further.

## 19. `RestClient` adapter: from HTTP status to meaningful errors

**`src/main/java/com/example/testboundary/HttpStockGateway.java`**

```java
package com.example.testboundary;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

@Component
public class HttpStockGateway implements StockGateway {

    private final RestClient client;

    public HttpStockGateway(
            RestClient.Builder builder,
            @Value("${demo.stock.base-url:http://127.0.0.1:9099}")
            String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    @Override
    public RemoteStock fetch(String sku) {
        try {
            RemoteStock stock = client.get()
                    .uri("/stock/{sku}", sku)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .onStatus(
                            HttpStatusCode::isError,
                            (request, response) -> {
                                if (response.getStatusCode()
                                        .value() == 503) {
                                    throw new UpstreamUnavailableException(
                                            "Downstream unavailable");
                                }
                                throw new UpstreamContractException(
                                        "Unexpected downstream HTTP status");
                            })
                    .body(RemoteStock.class);

            if (stock == null) {
                throw new UpstreamContractException(
                        "Empty downstream response");
            }

            return stock;
        } catch (ResourceAccessException networkFailure) {
            throw new UpstreamUnavailableException(
                    "Cannot access downstream service",
                    networkFailure);
        }
    }
}
```

**What this checks:**

- Downstream base URL comes from configuration, never from client input.
- `Accept: application/json` is set explicitly.
- `503` maps to a transient error for retry.
- Network I/O errors wrapped by `RestClient` into `ResourceAccessException` map to transient errors.
- Other HTTP error statuses map to contract failures (unretried in the demo).
- Empty JSON bodies count as contract failures.
- Schema/SKU checks remain in the service rather than assuming any deserializable JSON is business-valid.

**Important limitation:** This code **does not yet configure connect/read/overall timeouts** on the HTTP request factory. It serves to highlight test boundaries, **not as production-ready safety**. Before injecting latency/blackhole faults on real networks, configure finite timeouts on your project's HTTP client/request factory and test cancellation, connect/read limits, and retry budgets. Never send real traffic through a client that can hang forever calling it a safe chaos test. If a `@RestClientTest` slice configures a custom request factory, ensure the mock server still binds properly without getting overwritten.

## 20. Service: bounded retries and honest fallbacks

**`src/main/java/com/example/testboundary/InventoryService.java`**

```java
package com.example.testboundary;

import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private static final Pattern SKU =
            Pattern.compile("^[A-Z0-9-]{1,24}$");

    private static final Set<String> STOCK_VALUES =
            Set.of("AVAILABLE", "OUT_OF_STOCK");

    private final StockGateway gateway;

    public InventoryService(StockGateway gateway) {
        this.gateway = gateway;
    }

    public InventoryResponse check(String sku) {
        if (sku == null || !SKU.matcher(sku).matches()) {
            throw new InvalidSkuException();
        }

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                RemoteStock remote = gateway.fetch(sku);
                if (remote == null
                        || !sku.equals(remote.sku())
                        || !STOCK_VALUES.contains(
                                remote.stock())) {
                    throw new UpstreamContractException(
                            "Invalid downstream stock payload");
                }

                return new InventoryResponse(
                        sku, remote.stock(),
                        "REMOTE", false);

            } catch (UpstreamUnavailableException transientError) {
                if (attempt == 2) {
                    return new InventoryResponse(
                            sku, "UNKNOWN",
                            "FALLBACK", true);
                }
            }
        }

        throw new IllegalStateException(
                "Unreachable retry loop state");
    }
}
```

**Why not turn unavailable into `OUT_OF_STOCK`?** “Unknown” differs from “out of stock”. A misleading data fallback can wrongly block sales or misroute checkout. Systems with last-known-good caches can return stale values paired with freshness metadata and clear policies; never assume stale data is universally safe.

**Why retry only one exception type?** `UpstreamContractException` (bad schema or unexpected status) has no reason to heal immediately on retry. If production requires retrying 500/502/504 or 429 per policy, add matching tests rather than widening to `catch(RuntimeException)`. **Note:** This is an **instant retry with no backoff**, capped at 2 attempts so unit tests finish in milliseconds. During large outages, immediate retries double downstream RPS.

## 21. Controller and error advice

**`src/main/java/com/example/testboundary/InventoryController.java`**

```java
package com.example.testboundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/availability")
public class InventoryController {

    private final InventoryService service;

    public InventoryController(InventoryService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public InventoryResponse check(
            @PathVariable String sku) {
        return service.check(sku);
    }
}
```

**`src/main/java/com/example/testboundary/InventoryErrorAdvice.java`**

```java
package com.example.testboundary;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class InventoryErrorAdvice {

    public record ErrorBody(String code) {
    }

    @ExceptionHandler(InvalidSkuException.class)
    public ResponseEntity<ErrorBody> invalidSku() {
        return ResponseEntity.badRequest()
                .body(new ErrorBody("INVALID_SKU"));
    }

    @ExceptionHandler(UpstreamContractException.class)
    public ResponseEntity<ErrorBody> downstreamContract() {
        return ResponseEntity.status(502)
                .body(new ErrorBody("UPSTREAM_CONTRACT"));
    }
}
```

The controller contains no retry loop; error mapping sits separately. The endpoint returns 200 for `InventoryResponse` even with `degraded=true` as this demo's chosen contract. A production API might return 503 when stock is unknown; in that case functional tests, k6 checks, and SLOs must align accordingly.

**Error privacy:** Never leak stack traces, private hosts, credentials, or raw exception messages to callers. For unhandled unexpected errors, ensure Spring Boot error responses are sanitized. Never map arbitrary exceptions to 200/fallback, hiding security or contract defects.

## 22. Pure JUnit: per-request correctness and attempt counts

**`src/test/java/com/example/testboundary/InventoryServiceTest.java`**

```java
package com.example.testboundary;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class InventoryServiceTest {

    @Mock
    StockGateway gateway;

    InventoryService service;

    @BeforeEach
    void setUp() {
        service = new InventoryService(gateway);
    }

    @Test
    void healthyDownstreamReturnsBusinessData() {
        when(gateway.fetch("BOOK")).thenReturn(
                new RemoteStock("BOOK", "AVAILABLE"));

        InventoryResponse result = service.check("BOOK");

        assertEquals("AVAILABLE", result.status());
        assertEquals("REMOTE", result.source());
        assertFalse(result.degraded());
        verify(gateway).fetch("BOOK");
    }

    @Test
    void oneTransientFailureThenSuccessUsesTwoAttempts() {
        when(gateway.fetch("BOOK"))
                .thenThrow(new UpstreamUnavailableException(
                        "temporary 503"))
                .thenReturn(new RemoteStock(
                        "BOOK", "OUT_OF_STOCK"));

        InventoryResponse result = service.check("BOOK");

        assertEquals("OUT_OF_STOCK", result.status());
        assertFalse(result.degraded());
        verify(gateway, times(2)).fetch("BOOK");
    }

    @Test
    void repeated503UsesExplicitUnknownFallback() {
        when(gateway.fetch("BOOK"))
                .thenThrow(new UpstreamUnavailableException(
                        "temporary 503"));

        InventoryResponse result = service.check("BOOK");

        assertEquals("UNKNOWN", result.status());
        assertEquals("FALLBACK", result.source());
        assertTrue(result.degraded());
        verify(gateway, times(2)).fetch("BOOK");
    }

    @Test
    void contractErrorIsNotRetried() {
        when(gateway.fetch("BOOK"))
                .thenThrow(new UpstreamContractException(
                        "invalid JSON semantics"));

        assertThrows(UpstreamContractException.class,
                () -> service.check("BOOK"));

        verify(gateway).fetch("BOOK");
    }

    @Test
    void mismatchedRemoteSkuFailsClosed() {
        when(gateway.fetch("BOOK")).thenReturn(
                new RemoteStock("PEN", "AVAILABLE"));

        assertThrows(UpstreamContractException.class,
                () -> service.check("BOOK"));

        verify(gateway).fetch("BOOK");
    }

    @Test
    void invalidSkuNeverCallsDownstream() {
        assertThrows(InvalidSkuException.class,
                () -> service.check("book/../admin"));

        verifyNoInteractions(gateway);
    }
}
```

**These six methods** run **without a Spring context or HTTP sockets**. They prove exact policies: first-attempt success, single retry, exhausted retries, contract fail-closed, response SKU matching, and input validation. No latency or RPS assertions appear here. No `Thread.sleep` or live outage is required to verify exact retry counts.

**`repeated503UsesExplicitUnknownFallback` is a functional resilience test, not a load test.** It executes zero concurrent requests and measures no saturation. Anyone claiming “the server handles 1,000 RPS because this test passed” must be corrected immediately.

## 23. `@RestClientTest`: HTTP contracts and status mapping

**`src/test/java/com/example/testboundary/HttpStockGatewayTest.java`**

```java
package com.example.testboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(HttpStockGateway.class)
@TestPropertySource(properties =
        "demo.stock.base-url=http://stock.example.test")
class HttpStockGatewayTest {

    private static final String URL =
            "http://stock.example.test/stock/BOOK";

    @Autowired
    HttpStockGateway gateway;

    @Autowired
    MockRestServiceServer server;

    @Test
    void maps200JsonAndChecksRequestContract() {
        server.expect(requestTo(URL))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andRespond(withSuccess(
                        "{\"sku\":\"BOOK\",\"stock\":\"AVAILABLE\"}",
                        MediaType.APPLICATION_JSON));

        RemoteStock reply = gateway.fetch("BOOK");

        assertEquals("BOOK", reply.sku());
        assertEquals("AVAILABLE", reply.stock());
        server.verify();
    }

    @Test
    void maps503ToRetryableDomainException() {
        server.expect(requestTo(URL))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(
                        HttpStatus.SERVICE_UNAVAILABLE));

        assertThrows(UpstreamUnavailableException.class,
                () -> gateway.fetch("BOOK"));

        server.verify();
    }

    @Test
    void doesNotConfuse404With503() {
        server.expect(requestTo(URL))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(UpstreamContractException.class,
                () -> gateway.fetch("BOOK"));

        server.verify();
    }

    @Test
    void emptySuccessfulBodyIsContractFailure() {
        server.expect(requestTo(URL))
                .andRespond(withSuccess(
                        "", MediaType.APPLICATION_JSON));

        assertThrows(UpstreamContractException.class,
                () -> gateway.fetch("BOOK"));

        server.verify();
    }
}
```

**Four methods** prove the adapter sets URL/GET/`Accept` properly and maps 503/404/empty bodies per the demo contract. `MockRestServiceServer` plugs into `RestClient`'s request factory and **opens no connection to `stock.example.test`**. The mock server never executes real network timeouts, TLS, or connection resets, so `503` returns immediately without revealing thread-pool starvation under a 30-second hang.

To test client connection timeouts, DNS, redirects, TLS, or pool reuse, switch to a real mock HTTP server or Toxiproxy with the production request factory rather than extrapolating from this slice.

## 24. `@WebMvcTest`: public API contract

**`src/test/java/com/example/testboundary/InventoryControllerTest.java`**

```java
package com.example.testboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InventoryController.class)
@Import(InventoryErrorAdvice.class)
class InventoryControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    InventoryService service;

    @Test
    void successfulResultKeepsBusinessFields()
            throws Exception {
        when(service.check("BOOK"))
                .thenReturn(new InventoryResponse(
                        "BOOK", "AVAILABLE",
                        "REMOTE", false));

        mvc.perform(get("/api/availability/BOOK"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.sku").value("BOOK"),
                        jsonPath("$.status").value("AVAILABLE"),
                        jsonPath("$.source").value("REMOTE"),
                        jsonPath("$.degraded").value(false));

        verify(service).check("BOOK");
    }

    @Test
    void degradedResponseIsNotMisrepresentedAsStockAvailable()
            throws Exception {
        when(service.check("BOOK"))
                .thenReturn(new InventoryResponse(
                        "BOOK", "UNKNOWN",
                        "FALLBACK", true));

        mvc.perform(get("/api/availability/BOOK"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.status").value("UNKNOWN"),
                        jsonPath("$.source").value("FALLBACK"),
                        jsonPath("$.degraded").value(true));
    }

    @Test
    void invalidSkuMapsTo400WithoutLeakingDetails()
            throws Exception {
        when(service.check("bad"))
                .thenThrow(new InvalidSkuException());

        mvc.perform(get("/api/availability/bad"))
                .andExpectAll(
                        status().isBadRequest(),
                        jsonPath("$.code").value("INVALID_SKU"));
    }

    @Test
    void badDownstreamContractMapsTo502()
            throws Exception {
        when(service.check("BOOK"))
                .thenThrow(new UpstreamContractException(
                        "do not expose private backend detail"));

        mvc.perform(get("/api/availability/BOOK"))
                .andExpectAll(
                        status().isBadGateway(),
                        jsonPath("$.code").value(
                                "UPSTREAM_CONTRACT"));
    }
}
```

**Four methods** verify Spring MVC routing, JSON, and error mapping, while `InventoryService` is mocked. Returning the right controller payload does not prove the retry loop runs—that belongs to `InventoryServiceTest` in section 22, and never extrapolate downstream or network capacity from an MVC slice.

## 25. `@SpringBootTest(RANDOM_PORT)`: real inbound HTTP, mocked downstream

**`src/test/java/com/example/testboundary/InventoryHttpIntegrationTest.java`**

```java
package com.example.testboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InventoryHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @MockitoBean
    StockGateway gateway;

    @Test
    void actualInboundHttpReturnsHealthyContract() {
        when(gateway.fetch("BOOK")).thenReturn(
                new RemoteStock("BOOK", "AVAILABLE"));

        ResponseEntity<InventoryResponse> result =
                http.getForEntity(
                        "/api/availability/BOOK",
                        InventoryResponse.class);

        assertEquals(200, result.getStatusCode().value());
        assertEquals("BOOK", result.getBody().sku());
        assertEquals("AVAILABLE", result.getBody().status());
        assertFalse(result.getBody().degraded());

        verify(gateway).fetch("BOOK");
    }

    @Test
    void actualInboundHttpPreservesDegradedMarker() {
        when(gateway.fetch("BOOK"))
                .thenThrow(new UpstreamUnavailableException(
                        "transient fault"));

        ResponseEntity<InventoryResponse> result =
                http.getForEntity(
                        "/api/availability/BOOK",
                        InventoryResponse.class);

        assertEquals(200, result.getStatusCode().value());
        assertEquals("UNKNOWN", result.getBody().status());
        assertTrue(result.getBody().degraded());

        verify(gateway, times(2)).fetch("BOOK");
    }
}
```

**Two methods** boot a real server on a random port and call localhost HTTP via `TestRestTemplate`. They verify serialization and inbound transport more faithfully than MockMvc. However, `@MockitoBean StockGateway` replaces the downstream port, so **zero HTTP calls go to the stock service** in these two tests. Never claim “network fault recovered” from this suite.

Notably, Spring Boot warns that with `@Transactional` on a `RANDOM_PORT` test, client and server run on separate threads/transactions so test-thread rollback **does not roll back server-side changes**. This demo has no DB, yet workload/performance tests must isolate fixtures and cleanup explicitly.

## 26. Running the JUnit suite and result scope

| Class | `@Test` count | What is verified |
|---|---:|---|
| `InventoryServiceTest` | 6 | Domain validation, retry counts, fallback semantics |
| `HttpStockGatewayTest` | 4 | Outbound HTTP requests and status mapping via mock factory |
| `InventoryControllerTest` | 4 | Public HTTP JSON/errors via MockMvc |
| `InventoryHttpIntegrationTest` | 2 | Real inbound HTTP, mocked downstream |
| **Total** | **16** | Functional/API checks and controlled failure branches |

Run with the generated Gradle wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Expected result:** On JDK 17, Spring Boot 3.5.16, and resolved dependencies, all 16 tests are expected to pass. If the wrapper is missing, generate it per convention first. JUnit reports appear in `build/reports/tests/test/index.html`. This is an **assessment of the sample code**, **not a log of an executed Gradle run**. There is no fixed business stdout; random ports, CI timings, and request logs must never be hardcoded.

**Accurate conclusion:** When all 16 tests pass, you may state “functional contracts and controlled 503 handling for the tested scenarios are satisfied”. You **cannot** claim “99.9% SLO met” or “chaos recovery verified”, because no workload or real network fault experiment has run.

## 27. k6: standalone load script with safety guard

**`load/availability.js`** — JavaScript for the k6 tool, **not** executed by JUnit:

```javascript
import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';

const businessHealthy = new Rate('business_healthy');
const base = __ENV.BASE_URL || 'http://127.0.0.1:8080';

// Guard intentionally restricts target to loopback in this example.
// Change only after explicit approval for an isolated environment.
if (!/^http:\/\/(127\.0\.0\.1|localhost):[0-9]+$/.test(base)) {
  throw new Error('This training load script only targets loopback');
}

export const options = {
  scenarios: {
    availability: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 20
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{route:availability}': ['p(95)<500'],
    business_healthy: ['rate>0.99'],
    dropped_iterations: ['count==0']
  }
};

export default function () {
  const response = http.get(
    base + '/api/availability/BOOK',
    { tags: { route: 'availability' } }
  );

  let payload = null;
  try {
    payload = response.json();
  } catch (_error) {
    // JSON parse errors are counted as business failures below.
  }

  const valid =
    response.status === 200 &&
    payload !== null &&
    payload.sku === 'BOOK' &&
    payload.status === 'AVAILABLE' &&
    payload.source === 'REMOTE' &&
    payload.degraded === false;

  businessHealthy.add(valid);

  check(response, {
    'HTTP status 200': (r) => r.status === 200
  });
}
```

**Before running:** Start the Spring Boot app on port 8080 and an **isolated test downstream** returning `{"sku":"BOOK","stock":"AVAILABLE"}` at `http://127.0.0.1:9099/stock/BOOK`, or point `demo.stock.base-url` to your isolated stub. Without a downstream, the demo returns `UNKNOWN/degraded=true`; the script **intentionally fails `business_healthy`**, even while HTTP status stays 200.

Suggested command after installing k6 separately and verifying local environment authorization:

```bash
k6 run load/availability.js
```

Target a different local port:

```bash
BASE_URL=http://127.0.0.1:8081 k6 run load/availability.js
```

Inline env assignment is POSIX shell syntax; in PowerShell, set `$env:BASE_URL="http://127.0.0.1:8081"` and then run `k6 run load/availability.js`. **Do not run** before the upstream stub and readiness are stable, or you will measure the fallback path rather than the intended healthy baseline.

### 27.1. Meaning of the thresholds

- `http_req_failed: rate<0.01`: fraction of HTTP requests k6 considers failed is below 1%.
- `http_req_duration{route:availability}: p(95)<500`: 95% of requests tagged with this route finish under 500 ms (sample value).
- `business_healthy: rate>0.99`: >99% of requests return valid JSON with **`degraded === false`**.
- `dropped_iterations: count==0`: the load generator did not drop iterations due to insufficient VUs/capacity.

**A failing `check(...)` alone does not cause k6 to exit nonzero**; `thresholds` decide overall pass/fail. The custom `Rate` metric captures the **business SLI** instead of HTTP status alone. On HTTP 200 with `UNKNOWN`, `http_req_failed` stays false while `business_healthy` records false.

### 27.2. Limitations of the script

A **30-second × 10 iterations/s** script is a lab sanity load, not evidence for a production SLO. If the gateway has latency/timeouts, backlogs/caching, or an under-provisioned load generator, always archive achieved iteration rates and dropped iterations. Running k6 on a developer laptop alongside the app and stub creates bottlenecks very different from a production cluster. Never extrapolate CPU headroom, DB pools, or autoscaling from localhost runs.

## 28. Reading a k6 report without fooling yourself

Consider an *illustrative* report:

```text
http_req_duration...........: p(95)=120ms
http_req_failed.............: 0.00%
business_healthy............: 50.00%
dropped_iterations..........: 0
```

**Never call this PASS just because p95 is 120 ms and HTTP errors are 0%.** Half the responses degraded, failing the >99% business target. Investigate the backend and fallback cause; the k6 threshold rightly turns this into a failing exit code.

Another case:

```text
http_req_duration...........: p(95)=150ms
business_healthy............: 100.00%
dropped_iterations..........: 80
```

Launched requests were fast, yet the generator failed to dispatch all offered arrivals; the target workload was never reached. Never report p95 from a reduced rate as proof the system sustained the full target load.

### 28.1. Percentiles require sample sizes and segmentation

When 503 rates are high, measuring p95 only on successful responses makes p95 **artificially flattering**. Report both overall and segmented metrics (success, degraded, error) with sample counts. Measure both on the load generator and in server observability, noting anything unmeasured. Percentiles from a tiny sample or a single run on a busy CI box cannot justify long-term SLOs.

## 29. Real HTTP fault injection with WireMock

`MockRestServiceServer` in section 23 uses no sockets. To test read timeouts, connection resets, or redirect handling on the **real `RestClient` request factory**, run a **local `WireMockServer`** or `MockWebServer` on a random port and point `demo.stock.base-url` at it.

Illustrative Java WireMock **snippet** (requires adding a matching `wiremock` test dependency; not part of the runnable core project):

```java
// Illustrative snippet for local HTTP stub; requires WireMock imports.
WireMockServer stub = new WireMockServer(
        wireMockConfig().dynamicPort());

stub.start();
try {
    stub.stubFor(get(urlEqualTo("/stock/BOOK"))
            .willReturn(aResponse()
                    .withStatus(503)));

    // Instantiate real app/client pointing baseUrl to stub.baseUrl().
    // Assert retry budget/fallback over real HTTP calls.
    // stub.verify(2, getRequestedFor(urlEqualTo("/stock/BOOK")));
} finally {
    stub.stop();
}
```

To inject latency:

```java
// WireMock snippet; test client must configure finite timeouts.
stub.stubFor(get(urlEqualTo("/stock/BOOK"))
        .willReturn(aResponse()
                .withStatus(200)
                .withFixedDelay(1200)
                .withHeader("Content-Type", "application/json")
                .withBody(
                    "{\"sku\":\"BOOK\",\"stock\":\"AVAILABLE\"}")));
```

If the client read timeout is 500 ms, a 1,200 ms delay can trigger timeout and enter the failure path; yet **never assert the outcome without testing the exact request factory**. HTTP client libraries differ in connect/read/overall timeouts, auto-retries, connection pooling, and interrupted-response handling. Real tests should assert attempt counts, bounded elapsed time, zero leaked connections, fallback behavior, and recovery once the stub turns healthy.

**Never treat `withFixedDelay(1200)` as a production overload experiment.** It tests one local stub delay; it does not simulate CPU throttling, TCP packet loss, or DB lock contention.

## 30. Toxiproxy: faults at the TCP/network boundary

Testcontainers Toxiproxy places a proxy between the app/client and a downstream test container, letting you inject toxics such as:

```java
// Snippet; requires Testcontainers Toxiproxy module + Docker.
// proxy is a ContainerProxy created for the test upstream.
proxy.toxics()
        .latency(
                "latency-test",
                ToxicDirection.DOWNSTREAM,
                1100)
        .setJitter(100);

try {
    // Call real HTTP client targeting the proxy host/port.
    // Observe timeouts, retries, and degraded SLIs.
} finally {
    proxy.toxics().get("latency-test").remove();
}
```

**A different layer than WireMock status stubs:** Toxiproxy acts on the TCP stream (latency, bandwidth, timeouts, connection cuts), testing real network behavior. However, only connections **passing through the proxy** feel the toxic; if `RestClient` keeps a direct base URL or reuses an unproxied connection, the test misses the boundary.

Run Docker/Testcontainers only in authorized test environments, **never** proxying customer systems. Always remove toxics in `finally`; for long/remote experiments use TTLs and out-of-process operator rollback because Java `finally` will not run after `kill -9`.

### 30.1. Good questions for network fault tests

- When downstream delays 1,200 ms against a 500 ms timeout, does the API respond per contract within a **bounded total duration**?
- When timeouts occur, are retries strictly bounded?
- Does the connection pool leak or saturate without releasing connections?
- How much do business SLIs and queues shift during a 10-second downstream cut?
- When the toxic is removed, does the system recover to baseline within the expected window?
- Are degraded states tagged accurately in responses and metrics?
- Are GET retries safe while POST retries carry idempotency keys?

## 31. Timeouts, retry budgets, exponential backoff, and jitter

A production retry policy needs all of these together:

1. **Connect timeout** and **read/response timeout** tuned per downstream.
2. **Overall request deadline**, spanning all attempts and delays.
3. **Maximum attempts**, distinguishing retryable exceptions/statuses.
4. **Backoff and jitter** to avoid synchronized request storms.
5. **Retry budget** capping total retry volume per user/service.
6. **Idempotency semantics**: GET is typically safer than mutating payment POSTs, though even GET can trigger unusual backend side effects.
7. **Cancellation** when the caller disconnects or the deadline expires.
8. **Observability**: attempt counts, exhausted retries, fallback rates, circuit state.

Example with 2 attempts and 100 RPS arrival rate:

```text
Input to API:               100 requests/s
If each downstream call fails and is retried once:
Potential outbound attempts: ~200 calls/s
If 3 service layers each retry 2 times:
Worst-case attempt multiplication can grow dramatically.
```

That is **retry amplification**. A unit test asserting 2 calls is necessary, yet does not prove 2 calls are safe under load. Verify network/worker capacity and retry rates in load/fault experiments.

### 31.1. Never retry unrecoverable errors

Never blindly retry:

- `400` invalid input.
- `401` invalid/expired token without authorized refresh logic.
- `403` missing permissions.
- `404` when the contract confirms the resource does not exist.
- Malformed JSON schema / mismatched response SKU.
- Non-idempotent POSTs that may have committed before the response dropped.

HTTP 429 with `Retry-After` requires its own policy. The demo retries only 503 and I/O failures as an explicit scope, without assuming every 5xx behaves identically.

## 32. Circuit breakers, bulkheads, and fallbacks: exact meaning of each

**Retry:** re-attempts a transiently failing operation. Does not heal an overloaded upstream when every caller retries simultaneously.

**Circuit breaker:** tracks failures over a window and blocks calls once thresholds breach, typically cycling CLOSED/OPEN/HALF_OPEN. Tests must verify state transitions per policy, not merely catching one exception.

**Bulkhead:** caps concurrent tasks/connections so one integration cannot starve the entire thread/connection pool, isolating the rest of the service.

**Rate limiter:** caps request traffic, unlike a circuit breaker (which reacts to failures). **Timeout:** caps waiting time, unlike retries (attempt count).

**Fallback:** returns an approved alternative response (cached read, unknown, async receipt) per domain rules. A wrong business fallback can be worse than HTTP 503. Never return `available=false` as a fallback during an inventory outage if the UI must distinguish “out of stock” from “unknown”.

Real Spring Boot apps may use Resilience4j/Spring Cloud CircuitBreaker or client-specific policies. Tests must exercise real configured aspects/interceptors; **Mockito throwing an exception inside a service does not prove circuit breaker annotations or bulkhead wiring ran**.

## 33. Impact beyond the API: data, idempotency, and side effects

For read-only stock checks, an `UNKNOWN` fallback is fairly safe. Yet **mutating operations**—payments, emails, ticket reservations—require stricter fault tests:

- Network timeouts can occur **after** downstream committed.
- Retrying POST without an idempotency key can create two transactions.
- `at-least-once` message brokers can redeliver duplicates.
- During DB failover, a transaction may commit while the client remains unaware.
- Circuit breakers/fallbacks turning “payment pending” into “payment failed” trick users into double-submitting.
- Test-thread transaction rollbacks do not undo server-side commits in real HTTP tests.
- Load tests that mutate data without cleanup pollute datasets and skew measured capacity.

For mutating APIs, assert state **before and after** faults, idempotency keys, outboxes/unique constraints, and DB/queue postconditions—never assume a response code guarantees business integrity.

## 34. Observing the system: four golden signals and business SLIs

In Spring Boot 3.5 with Actuator/Micrometer, HTTP server observations emit metrics such as `http.server.requests` per configuration. To interpret an experiment cleanly, monitor:

- **Latency:** client and server p50/p95/p99, segmented by endpoint/status/degraded.
- **Traffic:** incoming RPS, outbound attempts/RPS, concurrency.
- **Errors:** 4xx/5xx, connection failures, timeouts, malformed responses, exhausted retries.
- **Saturation:** CPU, memory, GC pauses, thread pools, HTTP connection pools, DB pools, event backlogs.
- **Business SLI:** availability outcomes (`REMOTE` vs. `FALLBACK`), checkout success, stale cache age.
- **Recovery:** time from fault removal until p95/errors/business SLIs return to baseline.
- **Integrity:** duplicate payments/orders, missing events, orphan records, retry side effects.

**Never inspect average latency alone.** Outliers dominate tail experience; p95 and p99 matter, paired with sample counts. Avoid high-cardinality user IDs or request IDs in metric tags—they inflate memory and costs and can overload metrics backends. Correlation/request IDs belong in structured logs and traces.

### 34.1. Relationship between p95 and throughput

A healthy p95 at 10 RPS promises nothing at 100 RPS. As saturation rises, queueing drives tail latency up sharply while throughput plateaus. A load test must inspect **achieved RPS, drops, latency, business success, and saturation together** before drawing capacity conclusions for that workload.

## 35. Designing an experiment: hypothesis, blast radius, abort, rollback

A fault experiment needs an “experiment card”:

| Field | Verifiable example |
|---|---|
| Hypothesis | When stock stub returns 503 for 10 s, GET returns `UNKNOWN`/degraded within overall deadline and recovers after fault removal |
| Scope | Local Docker network, one app instance, one stub URL |
| Workload | 5 RPS, max 30 s, test SKU `BOOK`, zero persistent writes |
| Fault | HTTP 503 for 10 s, or 1.2 s network latency |
| Baseline | Healthy 200, 100% business success, measured prior p95 |
| During condition | Bounded retries, fallback observed, no runaway connections |
| Abort | CPU/heap/queue exceeds test bounds or impact spills outside allowlist |
| Rollback | Reset stub / remove toxic, stop containers, verify connections recover |
| Recovery criteria | Healthy rate and p95 return within baseline range over defined window |
| Evidence | Config commit, tool versions, metrics, request logs, timeline, outcome, remaining risks |

**Never fabricate “recovered in 3 seconds”** without actually observing it. Define goals beforehand, then record actual metrics and variances. Only revise thresholds after revisiting requirements—never lower the bar just to turn red into green.

## 36. Authorization and safety before injecting faults

An unauthorized fault/chaos experiment can disrupt users or corrupt data. Minimum safeguards:

1. **Isolated environment** by default; never target production or shared systems.
2. Clear **owner**, service scope, synthetic data, and time limit.
3. Least-privilege test accounts/credentials, network allowlists, and namespaces.
4. Bounded RPS/concurrency/CPU—no unbounded stress or unstoppable loops.
5. Preflight dashboards, alerts, runbooks, and rollbacks ready before injecting faults.
6. Continuous **abort triggers**; halt workload and clear faults on breach.
7. Clean up test resources/containers/records; archive evidence and check for orphan objects.
8. If production chaos is ever required, follow dedicated change/incident approvals with small canaries and SLO/error-budget guards. This lesson **grants no authority** to do so.

**Never “kill a production pod just to see what happens”.** Detailed testing belongs in the right environment with proper authorization. This lesson's load script guards targets to loopback only; clarify scope and obtain approval before modifying that guard for staging.

## 37. CI/CD: pipeline by signal and risk

| CI tier | When | Checks | Failure conditions |
|---|---|---|---|
| PR every commit | Fast | Unit/contract/controller/client slices | Wrong status/schema/retry count |
| PR or merge | Minutes | Full Spring integration + isolated dependencies | Broken wiring/HTTP/DB side effects |
| Nightly | Stable environment | Baseline load with thresholds | Missed p95, business success, or RPS |
| Scheduled resilience | Separate from shared CI | WireMock/Toxiproxy faults under bounded load | Fails to degrade/recover, or duplicates |
| Release candidate | Production-like topology | Soak/stress/controlled failover | Capacity/availability/integrity failure |
| Production operations | Explicitly approved | Synthetic probes / chaos canary if permitted | Runbook abort/rollback |

**You do not need heavy stress/chaos on every PR.** They are expensive, contend for resources, and need preflight/rollback controls. PRs should guard functional behavior cheaply; nightly/pre-release tiers raise fidelity. Archive **test configurations and environment versions** to compare runs fairly.

## 38. Fallacies when interpreting test results

| False conclusion | Why it's wrong | Accurate statement |
|---|---|---|
| “JUnit passed, so the system handles 1,000 RPS” | No workload was applied | “Contract passed on tested inputs” |
| “`MockRestServiceServer` returned 503, so network outages are tested” | No real sockets | “Verified response/error handling via mock factory” |
| “Load test had 0% HTTP errors, so users were unaffected” | Degraded 200s went uncounted | Measure business SLIs and payloads |
| “p95 looks great, so no issues” | Achieved throughput/drops may be poor | Report achieved RPS and dropped iterations |
| “One 200 response proves p99” | No distribution | Measure adequate samples over time |
| “Staging stress test equals production” | Topology/datasets differ | Document similarities and gaps |
| “Chaos test kept returning 200, so it recovered” | May be stuck in fallback forever | Verify healthy rate after fault removal |
| “Two retries always improve availability” | Retry storms during outages | Add retry budgets, backoff, circuit breakers |
| “`AT_LEAST_ONCE` means exactly once” | Duplicates can occur | Add idempotency/outbox tests |
| “Test DB rollback prevents real HTTP writes” | Transactions live on separate threads | Verify server-side state directly |
| “Running k6 from a laptop measures cluster capacity” | Different generator/network | Record topology and measure saturation |
| “503 means a permissions failure” | Upstream-specific status | Map errors per contract |
| “Chaos needs no rollback because `finally` cleans up” | `kill -9` skips `finally` | Enforce TTLs + external recovery |
| “Adjust p95 target to match the observed run” | Turns thresholds into vanity metrics | Set targets from SLOs beforehand |
| “Mockito circuit-breaker exception tests suffice” | Aspects/wiring may never run | Test configured circuit states at runtime |
| “Failing k6 `check` makes k6 exit nonzero” | Checks alone do not fail runs | Use `thresholds` |

## 39. Exercises and suggested answers

### A — Functional or load?

A test sends 100 sequential requests and asserts status 200 on each. Is this a load test proving concurrency?

**Answer:** No. That is functional repetition without an arrival model, target concurrency, latency distributions, achieved RPS, or saturation metrics. Use a workload generator with profiles and thresholds to measure load.

### B — Mocked 503 vs. chaos

In `@RestClientTest`, `MockRestServiceServer` returns 503. Someone claims “network outage recovery is verified”. What is wrong?

**Answer:** The mock factory opens no TCP sockets and simulates no real network cuts. It only verifies the adapter maps 503. Testing network-outage recovery needs WireMock, Toxiproxy, or cluster faults.

### C — Retrying 503

The gateway fails attempt 1 and succeeds on attempt 2. What are the expected attempt count and `degraded` flag?

**Answer:** Two attempts, final `source=REMOTE`, and `degraded=false`. Reject 3+ attempts if the retry budget is 2.

### D — Fallback 200

Half of responses return `UNKNOWN/degraded=true` with HTTP 200. Will `http_req_failed` reflect the 50% business failure rate?

**Answer:** No. You need a domain metric/check such as `business_healthy` with its own threshold.

### E — Missing load

k6 targets 100 iterations/s yet `dropped_iterations=1,000`. Can you conclude the app handles 100 RPS from p95?

**Answer:** No. Offered rate and achieved rate diverged; either the generator or the system fell behind the workload. Inspect drops, VU allocation, and request counts.

### F — Percentiles

5 requests take 10, 15, 20, 30, and 5,000 ms. Can average and p95 reliably characterize user experience?

**Answer:** No. The sample is far too small with a huge outlier; run a long enough steady workload and report sample counts plus tail distribution.

### G — Restoration

An experiment injects 503 for 15 s, then resets the stub. Why is a recovery phase still required?

**Answer:** Circuit breakers, pools/queues, retries, and caches can continue failing after upstream heals. Measure time-to-healthy and postconditions.

### H — Side effects

A payment POST times out after committing; the client retries and creates two charges. Can a functional HTTP 503 test catch this if it never inspects DB/payment state?

**Answer:** No. You need idempotency keys/transactions/outboxes and side-effect assertions, not just HTTP response assertions.

### I — Load generator bottleneck

A k6 machine hits 100% CPU while the server sits at 20% CPU and dropped iterations climb. Where is the bottleneck?

**Answer:** You cannot claim the server hit its limit. Inspect load-generator resources, network, `preAllocatedVUs`, and switch to distributed or adequately sized generators.

### J — Circuit breaker

A test calls a `@CircuitBreaker`-annotated service via `new Service()` and asserts an exception. Does that prove AOP breaker wiring works?

**Answer:** No. Annotations on directly instantiated Java objects bypass Spring proxies; verify via the Spring context bean and real breaker state.

### K — Authorization to inject faults

A team wants to cut egress in a production namespace “to see if it holds up” without approval or rollback. What should you do?

**Answer:** Do not run it. Run on an isolated test topology, write a hypothesis/guardrails/owner, and obtain explicit approval if production testing is ever mandated.

### L — Correctness vs. speed

A load test shows p95 under 100 ms, yet 10% of responses return the wrong SKU. Pass or fail?

**Answer:** Fail on business correctness regardless of low latency. Performance metrics never replace contract validation.

### M — Monitoring degraded mode

If an application intentionally returns `UNKNOWN` with HTTP 200 when upstream is down, what metrics should be added?

**Suggestion:** degraded response ratio, fallback cause, retry attempts, status by endpoint, and business-success SLI.

### N — Overall timeout

A client uses a 500 ms read timeout, 3 retries, and 200 ms backoff. Can the API promise completion within 500 ms?

**Answer:** No. Total elapsed time can exceed 500 ms across attempts, queueing, and connection setup. Enforce an overall time budget and test bounded real elapsed behavior.

### O — Load tests vs. PRs

A PR runs JUnit automatically on every commit. Should a 30-minute load test, breaking-point stress test, and network-partition chaos test run in that same default PR stage?

**Answer:** Usually no. Put those in nightly/release isolated environments with thresholds/guardrails; keep PRs focused on fast deterministic contract tests.

## 40. Review and acceptance checklist

- [ ] Every test's goal is phrased as a concrete question.
- [ ] Functional tests assert inputs, status, body, headers, and side effects accurately.
- [ ] Contract tests check consumer/provider semantics, not just stubbed JSON.
- [ ] `@WebMvcTest`/MockMvc is never labeled a real network test.
- [ ] `@RestClientTest`/`MockRestServiceServer` is never labeled a network outage test.
- [ ] `@SpringBootTest(RANDOM_PORT)` is clearly distinguished from MockMvc and mocked downstreams.
- [ ] Covered transient 503 → success and exhausted 503.
- [ ] Covered non-retryable contract errors.
- [ ] Retry attempts are bounded without catching all exceptions.
- [ ] Fallbacks never fabricate wrong business data.
- [ ] Degraded business responses carry explicit markers and dedicated metrics.
- [ ] Degraded HTTP 200s are never counted automatically as business successes.
- [ ] Connect, read, and overall timeouts are configured before real network-fault tests.
- [ ] Backoff, jitter, budgets, and circuit breakers exist for production-scale systems.
- [ ] Any retried mutating POST has an idempotency policy.
- [ ] DB/queue/external side effects under failure are checked where applicable.
- [ ] Workloads specify target RPS/VUs, duration, and dataset clearly.
- [ ] Understand how to choose an open vs. closed arrival model.
- [ ] k6 `checks` and `thresholds` are never confused.
- [ ] Tracking p95/p99 and sample counts, not averages alone.
- [ ] Tracking achieved RPS and `dropped_iterations`.
- [ ] Tracking saturation across app, DB, connection pools, and load generator.
- [ ] SLOs/thresholds set prior to runs from documented requirements.
- [ ] Capturing pre-fault baseline, during-fault behavior, and post-fault recovery.
- [ ] Fault type, intensity, TTL, and target explicitly documented.
- [ ] Faults affect only the intended network dependency.
- [ ] Fault experiments default to isolated environments with synthetic test data.
- [ ] Defined owner, blast radius, abort criteria, rollback, and cleanup.
- [ ] Never run unauthorized chaos against production or shared systems.
- [ ] Tests never touch customer data or leak secrets into logs.
- [ ] Archived metrics, traces, annotations, and timelines for each run.
- [ ] Distinguished simulated faults from real infrastructure failures.
- [ ] Checked recovery metrics and data integrity, not just status 200.
- [ ] Recorded environment topology, tool versions, and runtime versions.
- [ ] Acceptance notes separate actually executed runs from illustrative sample code.
- [ ] Never claimed load/chaos passes from a JUnit contract-only suite.

**Conclusion:** The boundary among these three test groups is the **boundary of evidence**. JUnit/MockMvc/`MockRestServiceServer` verify programmed *functional contracts and error handling* with extreme precision, yet measure neither throughput nor real network faults. k6 measures RPS, p95, and business SLIs under a defined workload, yet cannot replace branch-level correctness checks. WireMock/Toxiproxy and chaos experiments inject bounded failures to measure degradation, retry amplification, and recovery, provided they include **baselines, blast-radius limits, aborts, rollbacks, and postcondition checks**. Sound system assurance comes only from combining these results honestly with their scopes, hypotheses, and limits stated clearly.

### Official references

- Spring Boot 3.5.16 — Testing Spring Boot Applications, `@WebMvcTest`, `@RestClientTest`, and `RANDOM_PORT`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — `RestClient` status handlers/client factories: https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html
- Spring Boot 3.5 — Actuator/Micrometer metrics, `http.server.requests`: https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html
- Grafana k6 — Thresholds, `checks` vs. `thresholds`: https://grafana.com/docs/k6/latest/using-k6/thresholds/
- Grafana k6 — HTTP API load testing: https://grafana.com/docs/k6/latest/testing-guides/api-load-testing/
- Grafana k6 — Constant arrival rate executor: https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/
- Grafana k6 — Arrival rate, `preAllocatedVUs`, and dropped iterations: https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/arrival-rate-vu-allocation/
- WireMock — Simulating Faults (delays, resets, bad responses): https://wiremock.org/docs/simulating-faults/
- WireMock — Stubbing and Verifying HTTP interactions: https://wiremock.org/docs/stubbing/
- Testcontainers for Java — Toxiproxy network faults: https://java.testcontainers.org/modules/toxiproxy/
- Principles of Chaos Engineering — hypotheses, steady state, blast radius: https://principlesofchaos.org/
- Google SRE Workbook — Service Level Objectives and error budgets: https://sre.google/workbook/implementing-slos/

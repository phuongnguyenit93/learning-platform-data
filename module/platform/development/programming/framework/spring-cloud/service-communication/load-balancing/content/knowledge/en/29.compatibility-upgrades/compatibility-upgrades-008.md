# Regression Testing Configuration, Errors, Metrics, and Load Distribution

A Spring Boot or Spring Cloud upgrade can compile cleanly yet alter **Spring Cloud LoadBalancer** behavior: settings stop binding, the supplier chain gets replaced, exception mapping shifts, retries toggle differently than before, metrics vanish, or requests pile onto a subset of **`ServiceInstance`s**. These changes are rarely caught by a "context loads" test or a single HTTP request.

This lesson belongs to the **Compatibility and Upgrades** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. Its goal is to build a **pre- and post-upgrade regression test suite** for configuration, errors, Micrometer metrics, and load distribution, applicable to `RestClient`, `WebClient`, and OpenFeign. We will pin dependencies with the Spring Cloud BOM, check the compatibility matrix, stand up two counted backends, verify errors/retries, check meters, and compare request distribution against baseline.

> **Principle:** an upgrade is accepted only when critical contracts hold: the app uses a compatible version set, LoadBalancer reads the right configuration, errors classify accurately, metrics still reflect intended behavior, and traffic distributes within defined thresholds. Compare **baseline and target with the exact same scenario** to expose behavioral changes.

## 1. Regression Scope to Protect

| Area | Question to answer | Required evidence |
|---|---|---|
| Version compatibility | Are the Spring Boot and Spring Cloud release trains compatible? | BOM, dependency graph, startup/compatibility verifier |
| Configuration binding | Are retry, cache, health, zone, and metrics properties still bound? | Context startup and effective configuration assertions |
| Supplier/selection | Does the same service ID get the same candidate set and selection policy? | Two-instance test, selected instances, and handler counts |
| HTTP errors | Do 400/404/503, connect failures, and timeouts keep their contracts? | Statuses, exception types/causes, and error responses |
| Retry | Do retries match conditions, budget, and HTTP methods? | Request counts at backends, attempt counts |
| Metrics | Are meter names, tags, and counts still accurate? | `MeterRegistry` assertions and scrape output |
| Distribution | Do requests distribute per the intended algorithm/weights? | Per-backend counters and thresholded ratios |
| Performance/freshness | Did caching, discovery, timeouts, or latency regress? | p95/p99, source reads, stale windows |
| Runtime compatibility | Do `RestClient`, `WebClient`, and Feign integrations still work? | Integration tests per HTTP client |

Prioritize **contracts the application relies on**: service IDs, allowed target sets, request counts, response/error semantics, operational metrics, and distribution bounds. There is no need to assert every internal Spring Cloud detail if it is not part of the application's contract.

## 2. Lock Baseline Versions Before Upgrading

Spring Cloud ships as a **release train BOM**, where each train curates a set of project versions. Never bump **spring-cloud-loadbalancer** or **spring-cloud-commons** alone to a newer version while leaving the rest of Spring Cloud on an older train.

The official compatibility table currently lists typical mappings:

| Spring Cloud release train | Compatible Spring Boot generation | Notes |
|---|---|---|
| **2025.1.x (Oakwood)** | Boot 4.0.x; Boot 4.1.x from 2025.1.2 | Current train on the Spring Cloud page |
| **2025.0.x (Northfields)** | Boot 3.5.x | Check support policy before choosing |
| **2024.0.x (Moorgate)** | Boot 3.4.x | Check support policy before choosing |
| **2023.0.x (Leyton)** | Boot 3.2.x; Boot 3.3.x from 2023.0.2 | Older train; check EOL status |
| **2022.0.x (Kilburn)** | Boot 3.0.x; Boot 3.1.x from 2022.0.3 | Older train |
| **2021.0.x (Jubilee)** | Boot 2.6.x, 2.7.x | Older train |
| Earlier trains | Per corresponding release mapping | Mostly past end of support lifecycle |

This table **does not replace checking the support page at upgrade time**. The Spring Cloud page currently lists 2025.1.4 as the latest stable train; trains marked with an asterisk in the compatibility table are marked EOL. A release train may be technically compatible while already past OSS support. Always pick the latest service release within a still-supported train, read release notes, and verify official mappings before editing build files.

Source: https://spring.io/projects/spring-cloud/

### Gradle BOM Example

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

ext {
    springCloudVersion = '2025.1.4'
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is an illustrative example for Spring Boot 4.1.x with Spring Cloud 2025.1.x; this train supports Boot 4.1.x starting at 2025.1.2. Do not treat example versions as mandatory for every project. Pick **a version pair matching your baseline/target** and use the latest supported patch in the chosen release train.

### What Not to Do in a Single Upgrade

- Override individual versions of **spring-cloud-commons**, **spring-cloud-loadbalancer**, or **spring-cloud-openfeign** without a verified compatibility reason.
- Mix starters from different release trains.
- Pin standalone Spring Framework or Reactor versions as a "quick fix" for dependency convergence errors.
- Disable the compatibility verifier just to get the app to boot.
- Inspect only the build file without inspecting the **actual dependency graph**.

## 3. Capture a Reproducible Baseline and Target

Before changing versions, save baseline outputs:

~~~text
baseline/
  boot-version.txt
  spring-cloud-train.txt
  dependencies.txt
  startup.log
  configuration-report.txt
  error-contract.json
  metrics-snapshot.txt
  distribution.csv
  latency.csv
~~~

After upgrading, collect the identical dataset for the target. Every run should record Git commit/build identifier, JDK/runtime, Boot and Cloud versions, HTTP connector, discovery implementation, instance count, cache/health/retry settings, test seed/concurrency/request count, and logs/traces.

**Never compare two runs with differing conditions.** If baseline had two healthy instances while target had one instance or different concurrency, distribution skew cannot be attributed directly to the upgrade.

| Property | Baseline | Target | Criterion |
|---|---|---|---|
| Boot / Cloud BOM | Active version | Proposed version | Compatible per matrix |
| Dependency tree | Saved | Saved | No unintended version drift |
| Retry | Retries/statuses/methods | Target config | Same contract |
| Cache | TTL/implementation | Target config | Stale window within SLO |
| Errors | Status/cause mapping | Target mapping | Unchanged unless intentional |
| Metrics | Meter names/counts/tags | Target metrics | No lost signals |
| Distribution | A/B counters | A/B counters | Within bounds |
| Latency | p50/p95/p99 | p50/p95/p99 | Within regression budget |

## 4. Dependency Convergence and Startup Compatibility

A skewed dependency graph can compile against APIs yet load incompatible classes at runtime. In CI, export dependency reports before and after upgrading:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-loadbalancer --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
~~~

With Maven:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.cloud
mvn help:effective-pom
~~~

Verify:

- Only a single Spring Cloud release train BOM manages Cloud modules.
- No Spring Cloud module is overridden outside the BOM without a documented decision.
- Spring Boot, Spring Framework, Reactor, Micrometer, and HTTP clients are managed as a compatible set.
- Optional dependencies (Caffeine, Actuator, OpenFeign, discovery client) did not vanish from the target accidentally.
- No legacy dependency pulls in a different Spring Cloud Commons version.

Spring Cloud includes a compatibility verifier to catch certain incompatible version pairs. When startup reports a mismatch, fix the version pair per the release train. **Never disable the verifier just to ignore the error.** Override the verifier only with a documented technical reason, verified mapping, and governance approval.

## 5. Lock Down the Configuration Contract Before Upgrading

Properties directly affecting LoadBalancer behavior:

~~~yaml
spring:
  cloud:
    loadbalancer:
      enabled: true
      cache:
        enabled: true
        ttl: 20s
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retryable-status-codes:
          - 503
        retry-on-all-operations: false
      stats:
        micrometer:
          enabled: true
        include-path: false
~~~

This is illustrative configuration; verify effective properties against your active version. **`retry.enabled`**, **`cache.enabled`**, and **`stats.micrometer.enabled`** are global properties; do not assume every property overrides per client identically. LoadBalancer documentation distinguishes global properties from the per-client prefix **`spring.cloud.loadbalancer.clients.<clientId>.*`**.

Source: https://docs.spring.io/spring-cloud-commons/reference/configprops.html

### Configuration and Behavior Test Matrix

| Setting | Expected behavior | Test |
|---|---|---|
| `loadbalancer.enabled` | Client uses LB vs. skips LB | Call service ID and check destination |
| `cache.ttl` | Instance list ages per TTL | Warm cache, change source, measure convergence |
| `retry.enabled` | Retry on/off per integration | Backend request counter |
| `max-retries-on-next-service-instance` | Caps retries to another instance | A/B fail/success and count |
| `retryable-status-codes` | Retries only allowed statuses | 503 retries, 400 does not retry |
| `retry-on-all-operations` | Permits/forbids retries outside GET | Test POST and idempotency |
| `health-check.interval` | Probe cadence | Backend probe counter and eviction lag |
| `zone` / `hint` | Candidate set per policy | Assert candidate/selected instance |
| `stats.micrometer.enabled` | Registers LB meters | `MeterRegistry` assertion |
| `stats.include-path` | Controls URI tag cardinality | Inspect meter tags |

**Do not only assert that the property file contains a value.** Prove the application context bound it and runtime behavior reflects that configuration.

### Verifying Properties via Environment

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class LoadBalancerConfigurationRegressionTest {

    @Autowired
    Environment environment;

    @Test
    void criticalLoadBalancerPropertiesRemainConfigured() {
        assertThat(environment.getProperty(
            "spring.cloud.loadbalancer.enabled", Boolean.class))
            .isTrue();

        assertThat(environment.getProperty(
            "spring.cloud.loadbalancer.retry.enabled", Boolean.class))
            .isTrue();

        assertThat(environment.getProperty(
            "spring.cloud.loadbalancer.stats.micrometer.enabled",
            Boolean.class))
            .isTrue();

        assertThat(environment.getProperty(
            "spring.cloud.loadbalancer.retry.max-retries-on-next-service-instance",
            Integer.class))
            .isEqualTo(1);
    }
}
~~~

This test confirms properties exist in `Environment`; it **does not prove individual beans consumed them**. Combine it with behavioral integration tests in the sections below.

## 6. Build a Controllable Two-Backend Fixture

To test errors and load distribution, stand up two instances with distinct identities and request counters. Use JDK `HttpServer`, WireMock, or MockWebServer. Each handler should record `instanceId`, received request count, HTTP method/path, returned status, processing duration, and correlation ID if needed.

~~~text
catalog-a: http://127.0.0.1:<portA>
catalog-b: http://127.0.0.1:<portB>

catalog-service:
  instance A -> portA
  instance B -> portB
~~~

Controllable fault-injection states should include:

| Backend mode | Behavior |
|---|---|
| `HEALTHY` | HTTP 200, body contains `instanceId` |
| `UNAVAILABLE` | HTTP 503 |
| `BAD_REQUEST` | HTTP 400 |
| `SLOW` | Controlled delay exceeding read timeout |
| `CLOSE` | Close connection or reset if test server supports it |
| `MALFORMED_BODY` | HTTP 200 with undecodable body |

**Place counters inside the handler**, not solely on a mock client. On connection refused or no-instance, the backend handler count does not increment. When the server returns 503, the handler received the request and its count increments.

## 7. Integration Test Confirming Service ID and LoadBalancer Still Work

With `RestClient`, declare a **`@LoadBalanced`** builder:

~~~java
@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient catalogRestClient(
            @Qualifier("loadBalancedRestClientBuilder")
            RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Configure discovery in tests using **`SimpleDiscoveryClient`** and two dynamic URIs. Example properties once ports are known:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:18081
              - uri: http://127.0.0.1:18082
~~~

In CI, use dynamic ports via **`@DynamicPropertySource`** instead of fixed ports to avoid collisions. Send multiple requests:

~~~java
@Test
void loadBalancedClientCanReachBothHealthyInstances() {
    for (int i = 0; i < 100; i++) {
        catalogRestClient.get()
            .uri("/api/whoami")
            .retrieve()
            .toBodilessEntity();
    }

    assertThat(receivedA.get() + receivedB.get()).isEqualTo(100);
    assertThat(receivedA.get()).isPositive();
    assertThat(receivedB.get()).isPositive();
}
~~~

This is a minimal assertion: **both instances were reached**. Load distribution gets its own quantitative threshold tests below; do not use this test as proof of exact ratios.

After upgrading, if all requests hit only A, check whether the supplier still returns A/B, whether the service ID changed, whether health/zone/hint filters excluded B, whether cache holds a stale snapshot, whether `@LoadBalanced` still applies to the right bean, or whether the HTTP client switched to a fixed URL bypassing LB.

## 8. Regression Testing HTTP Errors

Lock down both **returned statuses** and client **exception/error mapping**. Example with `RestClient` and backends returning 503. Run this test in a context with retries disabled, such as `spring.cloud.loadbalancer.retry.enabled=false`, to measure a single response:

~~~java
@Test
void mapsServiceUnavailableFromBackend() {
    backendA.setMode(BackendMode.UNAVAILABLE);
    backendB.setMode(BackendMode.UNAVAILABLE);

    assertThatThrownBy(() ->
        catalogRestClient.get()
            .uri("/api/items/42")
            .retrieve()
            .body(String.class)
    ).isInstanceOf(HttpServerErrorException.ServiceUnavailable.class);

    // This test context disables LoadBalancer retry to measure a single HTTP response.
    assertThat(receivedA.get() + receivedB.get()).isEqualTo(1);
}
~~~

In real applications, exceptions may be translated by an adapter into `DownstreamCallException` or business errors. When upgrading, assert the **application exception promised by the business layer** rather than coupling tightly to internal HTTP-client exception classes if an adapter intentionally hides them.

### Minimum Error Matrix

| Fault | Backend received | Caller expectation | Retry |
|---|---:|---|---|
| HTTP 400 | 1 | Validation/rejected | No retry |
| HTTP 401/403 | 1 | Auth/authorization failure | No retry with same credentials |
| HTTP 404 per contract | 1 | Resource not found or `Optional.empty` | No retry |
| HTTP 409 | 1 | Conflict | Per contract |
| HTTP 429 | 1 per attempt | Rate limited | Conditionally per `Retry-After`/budget |
| HTTP 503 | 1 per attempt | Downstream unavailable | Only if policy allows |
| Connect refused | 0 at target handler | Transport failure | Conditional |
| Read timeout after request received | ≥1 | Timeout; outcome may be UNKNOWN | Cautious with POST |
| No `ServiceInstance` | 0 | No-instance/LB failure | Per discovery policy |
| 2xx body fails schema | 1 | Decode/contract failure | Usually no blind retry |

A backend 503 response and a no-instance failure can both surface as errors to the caller yet have different origins. Check handler counts and LoadBalancer discard metrics to distinguish them.

When comparing clients, note differing transport exceptions:

| Client | Error HTTP response | Pre-/non-HTTP-response error |
|---|---|---|
| `RestClient` | `RestClientResponseException` and subclasses | `ResourceAccessException` or I/O cause |
| `WebClient` | `WebClientResponseException` and subclasses | `WebClientRequestException`, timeout/cancel signal |
| OpenFeign | `FeignException` and subclasses | `RetryableException` or exceptions from `ErrorDecoder`/transport |

These classes do not have to match identically. If the app has a shared adapter, test the application error model after the adapter, while keeping a few integration tests to detect exception-mapping shifts per client.

## 9. Regression Testing Retry and Idempotency

Enable only one retry layer per test for clean measurement. Example:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retryable-status-codes:
          - 503
        retry-on-all-operations: false
~~~

Tests to include:

1. A returns 503, B returns 200: pin initial selection to A (or use a deterministic test supplier), then verify the caller retries onto B and handler counters record both requests.
2. Both A and B return 503: caller stops within budget without unbounded retries.
3. 400: zero retries.
4. GET: retries as allowed by policy.
5. POST: zero retries when `retry-on-all-operations=false`, unless explicit contract/idempotency is designed.
6. Timeout after server commit: outcome treated as UNKNOWN; retries never mint a new operation key for the same business intent.

**Never assume `max-retries-on-next-service-instance=1` always equals two total HTTP requests.** Failures can occur before the backend; errors may be ineligible for retry; transport/gateway layers can add retries. Count at each instance's handler.

### Budget Assertion

~~~java
@Test
void retryBudgetDoesNotCreateUnexpectedBackendRequests() {
    backendA.setMode(BackendMode.UNAVAILABLE);
    backendB.setMode(BackendMode.UNAVAILABLE);

    callThroughApplicationPort();

    assertThat(receivedA.get() + receivedB.get())
        .isLessThanOrEqualTo(EXPECTED_MAX_BACKEND_RECEIPTS);
}
~~~

`EXPECTED_MAX_BACKEND_RECEIPTS` must be determined for the exact policy/HTTP integration under test rather than copying a fixed number when other retry layers exist.

For POST, also count committed side effects. Two HTTP requests can still create only one transaction if idempotency is enforced via shared store/unique key; otherwise, a post-commit timeout causes retries to create duplicate data.

## 10. Checking Micrometer LoadBalancer Metrics

Spring Cloud LoadBalancer provides `MicrometerStatsLoadBalancerLifecycle`. To activate it, ensure `MeterRegistry` is present and enable:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
        include-path: false
~~~

With Actuator/Micrometer properly configured, active meters include:

| Meter | Type | Meaning |
|---|---|---|
| `loadbalancer.requests.active` | Gauge | Currently active requests tagged by service/instance where available |
| `loadbalancer.requests.success` | Timer | Requests finishing by handing a response back to the HTTP client |
| `loadbalancer.requests.failed` | Timer | Requests finishing with an exception |
| `loadbalancer.requests.discard` | Counter | Requests discarded because no instance could be selected |

**Important semantic note:** `loadbalancer.requests.success` does not mean business HTTP status 2xx. If LoadBalancer picks an instance and the HTTP client receives an HTTP 503 response, LoadBalancer lifecycle may still record delivering that response back to the client as success. Use separate HTTP/server metrics to track 4xx/5xx statuses.

Metrics may be registered **after the first recorded sample**; tests should not require meters to exist before any request runs.

### MeterRegistry Test

~~~java
@Autowired
MeterRegistry meterRegistry;

@Test
void recordsLoadBalancerMetricsAfterRequest() {
    Timer successBefore = meterRegistry.find(
        "loadbalancer.requests.success").timer();

    long before = successBefore == null ? 0 : successBefore.count();

    callThroughApplicationPort();

    Timer successAfter = meterRegistry.find(
        "loadbalancer.requests.success").timer();

    assertThat(successAfter).isNotNull();
    assertThat(successAfter.count()).isGreaterThan(before);
}
~~~

This is an illustrative template requiring Actuator/Micrometer and stats enabled. On a shared `MeterRegistry` in a Spring context, avoid arbitrary `clear()` calls if other tests share the registry. Snapshot the count before the request and assert it increases, or isolate contexts/registries per test.

For no-instance scenarios, check `loadbalancer.requests.discard` increments when the integration emits that meter. For connect/timeout failures, check the failed timer and exception traces. Never assume every client implementation populates the exact same tag set; some blocking integrations may omit request/response data.

### Avoid High Cardinality

The `uri` tag can contain paths. Dynamic paths like `/orders/12345` can create unbounded metric series. `spring.cloud.loadbalancer.stats.include-path=false` prevents including paths in the URI tag where supported. **Never put instance IDs, request IDs, user IDs, or raw URLs with query tokens into metric tags.**

## 11. Testing Load Distribution Across Two Instances

For Round Robin with two healthy instances and sequential requests, expect a near-balanced ratio. Over `N` requests:

~~~text
total = countA + countB
ratioA = countA / total
ratioB = countB / total
imbalance = abs(countA - countB) / total
~~~

Example 1,000-request test:

~~~java
@Test
void distributesSequentialRequestsAcrossTwoInstances() {
    int total = 1000;

    for (int i = 0; i < total; i++) {
        callThroughApplicationPort();
    }

    int a = receivedA.get();
    int b = receivedB.get();

    assertThat(a + b).isEqualTo(total);

    double ratioA = (double) a / total;
    double ratioB = (double) b / total;

    assertThat(ratioA).isBetween(0.45, 0.55);
    assertThat(ratioB).isBetween(0.45, 0.55);
}
~~~

The 45–55% band is **an example for sequential Round Robin tests**, not a default SLO. With `RandomLoadBalancer`, weighted suppliers, zone preferences, sticky sessions, subsets, retries, or concurrent calls, design bounds matching the actual algorithm and workload.

### Testing Weighted Routing

If weights and metadata for A:B are configured 80:20, do not assert an exact 4:1 cycle on every request unless the algorithm/implementation guarantees a fixed cycle. With a large enough sample size, assert within statistical bounds with safety margins:

~~~text
expected A share ≈ 0.80
expected B share ≈ 0.20
~~~

Thresholds must account for sample size, random/weighted policies, and acceptable false-failure rates. For deterministic weighted algorithms, tighter assertions can be used once that version's contract is verified.

### When Load Distribution Shifts After Upgrade

Check in order:

1. Does the candidate list before and after contain the same A/B?
2. Did weight or zone metadata change?
3. Is the algorithm still Round Robin, or was a custom LoadBalancer lost?
4. Did sticky sessions, hints, or headers change?
5. Are retries sending extra requests to certain instances?
6. Is one backend responding slower, shifting concurrency or timeouts?
7. Are counters counting health probes or out-of-test requests?

Do not jump to "the algorithm regressed" from one small-sample run. Repeat multiple runs under identical conditions and record distributions.

## 12. Regression Testing Cache and Health Checks

Caching and health checks can alter the candidate set even without config changes. Tests should verify:

- TTL and cache enabled/disabled settings per service client.
- Source updates reflect after TTL/refresh as in baseline.
- No unintended double caching.
- Unhealthy instances are evicted within the SLO window.
- When zero healthy instances remain, fallback behavior keeps its contract.
- Cache/health supplier chains are not overwritten when custom config loads.

Example scenario:

~~~text
t0: source = [A, B], warm cache
t1: B is deregistered or health=DOWN
t2: caller may still see stale [A, B]
t3: after expiry/refetch/health refresh, candidate list = [A]
~~~

Tests should never assert exact millisecond timings on CI. Use bounded deadlines, poll the candidate list, and measure detection delay. If a new release changes default TTL/health behavior, explicit config and tests catch it early.

## 13. Comparing RestClient, WebClient, and OpenFeign

All three can route through Spring Cloud LoadBalancer, yet their integrations and failures differ:

| Client | Common LB integration | Regressions to check |
|---|---|---|
| `RestClient` | `@LoadBalanced RestClient.Builder` | Request factory, URI rewrite, exceptions, lifecycle metrics |
| `WebClient` | `@LoadBalanced WebClient.Builder` or LoadBalancer exchange filter | Subscription/retries, Reactor errors, timeouts, cancellation |
| OpenFeign | `@FeignClient(name = "...")` with Spring Cloud LoadBalancer | Client bean, `Retryer`/`ErrorDecoder`, transport, URL overrides |

A client with a fixed URL or built without integration can bypass service IDs/LB. After upgrading, verify real requests reach A/B rather than merely checking annotations exist.

### One Shared Contract Across All Three Clients

The same test fixture should verify:

- Same logical service ID.
- Same allowed instance set.
- Same HTTP status/error semantics per adapter contract.
- Retry policies not unintentionally toggled differently.
- Metrics/traces emitted or equivalent observability present.
- Total backend requests and distribution stay within the regression budget.

Do not force exception classes across all three clients to be identical if adapters do not normalize them; instead assert the **application error model** at the business layer.

## 14. Regression Testing Per-Service-ID Configuration

Spring Cloud LoadBalancer builds an isolated child context per service ID. A custom config class accidentally picked up by component scan can affect multiple clients.

Verify:

- `@LoadBalancerClient(name = "catalog-service", ...)` affects only that service ID.
- Configuration classes are not unintentionally scanned as global beans.
- Suppliers/custom algorithms remain active after upgrading.
- `spring.cloud.loadbalancer.clients.<clientId>.*` overrides the expected properties.
- Global properties are not mistaken for per-client properties.

LoadBalancer docs explicitly state that properties like `enabled`, `retry.enabled`, `cache.enabled`, and `stats.micrometer.enabled` are global; per-client override behavior does not match every other property.

Source: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html

## 15. Testing Metrics and Distribution Under the Same Workload

A test workload can send 1,000 GET requests to a service ID. Collect simultaneously:

| Signal | Source |
|---|---|
| Logical calls | Test driver |
| Backend received A/B | Handler counters |
| HTTP 2xx/4xx/5xx | Client/server metrics |
| LB success/failed/discard | Micrometer LoadBalancer lifecycle |
| Selected instance | Traces/logs or request transformers |
| p50/p95/p99 | Timers/histograms |
| Retry count | Retry instrumentation |
| Candidate list | Discovery/supplier observations |

**Do not add meters of different kinds into one combined "request total."** `loadbalancer.requests.success` is a timer, `loadbalancer.requests.discard` is a counter, backend handler count measures received requests, and client attempts measure tries. Correlate these signals via correlation/trace IDs or a shared test window.

Example baseline/target output:

| Metric | Baseline | Target | Assessment |
|---|---:|---:|---|
| Backend A received | 502 | 498 | Within bounds |
| Backend B received | 498 | 502 | Within bounds |
| Total backend received | 1,000 | 1,000 | Preserved |
| HTTP 5xx | 0 | 0 | No increase |
| LB discard | 0 | 0 | No lost instances |
| p95 latency | 42 ms | 46 ms | +9.5%, compare vs. budget |
| Retry count | 0 | 0 | Unchanged |

Numbers in the table are **synthetic data illustrating report format**, not Spring Cloud benchmarks.

## 16. Pre- and Post-Upgrade CI Pipeline

A sound pipeline includes these stages:

~~~mermaid
flowchart TD
    A["Resolve BOM and dependency graph"] --> B["Compatibility verifier + application startup"]
    B --> C["Configuration binding regression"]
    C --> D["HTTP error and retry contracts"]
    D --> E["Metrics assertions"]
    E --> F["Two-instance distribution test"]
    F --> G["Cache/health/failure injection"]
    G --> H["Performance smoke and report"]
    H --> I{"All regression budgets pass?"}
    I -->|Yes| J["Canary / staged rollout"]
    I -->|No| K["Block upgrade; inspect diff"]
~~~

### Layered Test Suite

| Stage | Test type | Goal |
|---|---|---|
| Compile | Compile/test compile | Catch API/binary breaks |
| Dependency | Dependency tree/convergence | Catch version drift |
| Context | Startup/compatibility verifier | Catch mismatches and bean wiring errors |
| Configuration | Effective properties | Catch unbound properties |
| Unit | Error mapper/retry decisions | Lock down business semantics |
| Integration | Two backends + LoadBalancer | Verify service ID and instance selection |
| Observability | `MeterRegistry`/scrape | Preserve metric contracts |
| Distribution | 500–1,000+ requests | Detect skew |
| Fault injection | 503/timeout/no-instance | Verify failures and recovery |
| Performance smoke | p95/p99 | Catch latency regressions |

Do not run load-distribution tests in a noisy environment and use one noisy run to block every upgrade. Separate deterministic smoke tests from controlled performance tests.

## 17. Controlled Upgrade Procedure

1. **Select a compatible release train** based on Spring Boot version and support policy.
2. **Save the baseline** dependency graph, properties, metrics, error matrix, and distribution.
3. **Bump the BOM on a separate branch**, never updating individual Spring Cloud modules independently.
4. **Run compile and startup** to catch API/compatibility issues.
5. **Run configuration + integration regressions** with the exact same test fixtures.
6. **Compare metrics and distribution** against baseline using regression budgets.
7. **Read release notes** for the train and related projects (Commons, LoadBalancer, OpenFeign, discovery client).
8. **Canary a small caller group** and watch discard/failed/latency/retry/instance distribution.
9. **Ramp traffic gradually** once metrics stabilize; retain rollback artifacts/BOM.
10. **Document intentional changes** (e.g., changed default properties) with explicit sign-off.

### Example Rollback Triggers

- Compatibility verifier fails or context fails to start.
- Candidate list becomes unexpectedly empty.
- LB discards rise past baseline.
- 5xx/timeout rates exceed SLO.
- One instance receives traffic share exceeding defined thresholds.
- Retry counts spike or exceed budget.
- p95/p99 latency breaches the regression budget.
- Essential metrics disappear or tag cardinality explodes.

Rollbacks should follow agreed metrics and observation windows, not a single isolated log line.

## 18. Common Upgrade Pitfalls

1. Bumping Boot while keeping an incompatible Spring Cloud train.
2. Bumping `spring-cloud-loadbalancer` alone while leaving Commons/OpenFeign on another version.
3. Skipping the BOM or overriding dependency versions without control.
4. Disabling the compatibility verifier instead of fixing the version mapping.
5. Leaving old properties in YAML that no longer bind as expected.
6. Confusing global vs. per-client property prefixes.
7. Letting custom `@LoadBalancerClient` configs get picked up by component scan.
8. Changing cache/health/filter order in the supplier chain.
9. Changing retry defaults or retry exception allowlists.
10. Feign `Retryer`/`ErrorDecoder` differing after upgrade.
11. `RestClient`/`WebClient` builder losing `@LoadBalanced`.
12. Client using a fixed URL and bypassing LoadBalancer.
13. Micrometer LoadBalancer stats disabled or missing `MeterRegistry`.
14. Mistaking the `success` metric for HTTP 2xx.
15. Metric URIs containing dynamic paths, inflating cardinality.
16. Round Robin/weighted/zone policies drifting from expected behavior.
17. Missing or renamed instance weight/zone metadata keys.
18. Cache TTL or default cache implementation changing.
19. Discovery client having its own cache, causing double caching.
20. Tests counting mock invocations instead of backend receipts.
21. Distribution tests asserting exact 50/50 across every algorithm/concurrency mode.
22. Failing to separate connect errors, no-instance errors, and backend HTTP 503s.
23. Treating a post-side-effect timeout as guaranteed failure and retrying into duplicate data.
24. Lacking a baseline to tell regressions apart from natural load variation.
25. Running canaries too short or with too little traffic to detect skew.

## 19. Sign-Off Checklist

### Version and Build

- [ ] Spring Boot/Spring Cloud pair is in the compatibility matrix.
- [ ] Train is still supported and service release notes reviewed.
- [ ] Spring Cloud BOM manages modules within the same train.
- [ ] Dependency tree has no unexpected overrides.
- [ ] Compatibility verifier remains enabled.

### Configuration and Suppliers

- [ ] Critical properties bind properly.
- [ ] Global vs. per-client retry/cache/stats settings are distinguished.
- [ ] Custom LoadBalancer config targets the exact service ID.
- [ ] Supplier/health/cache/zone/weight chains preserve contracts.
- [ ] `RestClient`/`WebClient`/Feign genuinely route through LoadBalancer.

### Errors and Retries

- [ ] 400/401/403/404/409/429/503 map properly.
- [ ] No-instance is distinguished from backend 503.
- [ ] Connect failures are distinguished from read timeouts.
- [ ] Retries run only for permitted errors and methods.
- [ ] Backend handler counts stay within retry budget.
- [ ] Retried POSTs enforce idempotency.

### Metrics and Distribution

- [ ] LoadBalancer Micrometer stats enabled with `MeterRegistry` present.
- [ ] `success`/`failed`/`discard`/`active` semantics properly understood.
- [ ] HTTP status metrics tracked separately.
- [ ] URI/tag cardinality bounded.
- [ ] Request counters recorded across all backend instances.
- [ ] Distribution ratios fall within algorithm thresholds.
- [ ] p95/p99 and retry rates stay within budget.

### Release

- [ ] Baseline and target ran on identical fixtures and workloads.
- [ ] Regression report archived.
- [ ] Canary has explicit rollback triggers.
- [ ] Intentional changes documented clearly.

## 20. Conclusion

**Upgrade regression testing for Spring Cloud LoadBalancer must verify both configuration and runtime behavior.** The compatibility matrix and BOM select a coherent version set; context/property tests catch unbound settings; two counted backends verify errors, retries, and load distribution; and Micrometer exposes discards, failures, and latency. No single check replaces that full body of evidence.

When upgrading `RestClient`, `WebClient`, or OpenFeign integrations, compare **the same service ID, topology, fault injection, and workload** between baseline and target. Specifically, distinguish LoadBalancer metrics from HTTP statuses, backend receipts from client attempts, and Round Robin distribution from weighted/zone policies. A safe upgrade is one where defined contracts remain intact, every new difference has an explanation, and canaries provide clear signals to halt or roll back before issues spread.

## References

- Spring Cloud – Release train / Spring Boot compatibility and BOM: https://spring.io/projects/spring-cloud/
- Spring Cloud Commons – LoadBalancer, supplier configuration, Micrometer statistics, and per-client properties: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Cloud Commons – Configuration properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- Spring Cloud – Supported versions and support policy: https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions
- Spring Boot – Supported versions and dependency management: https://spring.io/projects/spring-boot




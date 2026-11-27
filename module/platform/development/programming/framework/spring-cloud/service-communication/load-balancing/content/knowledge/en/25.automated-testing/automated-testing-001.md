# Separating Unit Tests, Integration Tests, and Load Testing

**Spring Cloud LoadBalancer** might select the right `ServiceInstance` in a unit test, yet the HTTP request still fails because discovery, an interceptor, DNS, a connection pool, or a timeout is misconfigured. Conversely, an integration test that succeeds a few times does not prove that the system distributes load stably when concurrent requests surge.

Therefore, testing a microservices communication system requires **multiple verification layers, each answering a different question**:

- **Unit test:** *Are the selection algorithm, instance filtering policy, and fallback correct for the given input data?*
- **Integration test:** *Are the Spring components actually wired together properly; is the service ID resolved to a physical instance, and does the HTTP request reach the right destination?*
- **Load/performance test:** *Under the expected traffic and concurrency, do distribution, latency, throughput, and error rate stay within acceptable limits?*

This lesson belongs to the **Automated Testing** chapter of the Spring Cloud LoadBalancer module, covering discovery, `ServiceInstanceListSupplier`, health checks, zone/hint routing, `RestClient`, `WebClient`, OpenFeign, and interactions with retries/timeouts. The focus is on **dividing testing responsibilities** to achieve fast, stable feedback in CI while not missing failures that only appear when running the real system.

## 1. Testing model along LoadBalancer boundaries

An inter-service call can follow this flow:

~~~mermaid
flowchart TD
    A["Business code<br/>GET http://catalog-service/products/42"]
    B["@LoadBalanced RestClient / WebClient<br/>or OpenFeign"]
    C["Spring Cloud LoadBalancer<br/>selects a ServiceInstance"]
    D["ServiceInstanceListSupplier<br/>discovery, cache, health, zone"]
    E["HTTP transport<br/>pool, DNS, TCP/TLS, timeout"]
    F["catalog-service instance"]
    U["UNIT<br/>Tests policy, supplier, selection"]
    I["INTEGRATION<br/>Tests wiring and real HTTP requests"]
    L["LOAD<br/>Tests throughput, latency, fairness, saturation"]
    A --> B --> C
    C <--> D
    C --> E --> F
    U -.-> C
    U -.-> D
    I -.-> B
    I -.-> E
    L -.-> A
    L -.-> F
~~~

**Do not expect a single test type to cover every kind of failure.** You can use mocks to test a strict-region filter, but mocks will not catch a missing `@LoadBalanced` annotation. Conversely, you might successfully call a local endpoint without knowing whether the policy picks a forbidden instance under all data conditions.

| Comparison axis | Unit test | Integration test | Load test |
|---|---|---|---|
| Observed unit | Function, filter, supplier, selector | Spring context + HTTP client + fake discovery/registry | Call path from caller across instances |
| Network I/O | No | Yes, usually to an in-test server | Yes, with controlled simulated traffic |
| Instance source | Immutable list/fake supplier | `SimpleDiscoveryClient`, fake registry, Testcontainers | Discovery or production-like environment |
| Assertion type | Exact, deterministic, repeatable | Actual response, selected instance, errors/wiring | SLOs, distribution ratio, p95/p99, error rate, capacity |
| Feedback speed on code changes | Usually fastest | Slower due to context/server startup | Resource-intensive; run on schedule/gate |
| Best-detected defects | Faulty policies and edge cases | Dependencies, beans, URIs, interceptors, HTTP integration | Pool exhaustion, retry storms, latency tail, hotspots |
| What it does **not** prove | That HTTP transport works | Resilience under heavy load | Absolute correctness for all inputs |

Additional layers such as **contract tests** and **end-to-end tests** remain useful, but they do not replace these three layers: contract tests verify schemas/HTTP agreements; end-to-end tests verify a business flow across multiple services.

## 2. Designing acceptance criteria before writing tests

For example, `catalog-service` has two instances:

| Instance ID | URI | Zone | Weight |
|---|---|---|---:|
| `catalog-a` | `http://127.0.0.1:8081` | `zone-a` | 3 |
| `catalog-b` | `http://127.0.0.1:8082` | `zone-b` | 1 |

The `order-service` application calls the logical URL `http://catalog-service`. Before choosing testing tools, describe the rules you want to guarantee:

1. When the list is empty, **do not select** an arbitrary instance.
2. When using round-robin and both instances are valid, both have a chance of being selected.
3. When the policy requires **`zone-a` only**, if only `zone-b` remains, it must fail closed rather than crossing zones.
4. When using **soft zone preference**, if no instance exists in the preferred zone, it can fall back to the remaining list.
5. When `catalog-a` stops responding, the client does not hang beyond the timeout/retry budget.
6. Under target load, p95/p99 latency and error rate remain within agreed bounds; no single instance becomes unexpectedly overloaded.

Each rule can be verified at one or more layers, but **choose the lowest layer sufficient to prove it**. Rule 3 can be tested thoroughly with unit tests, followed by an integration test confirming the filter is properly bound to the service ID.

## 3. A test pyramid for Spring Cloud LoadBalancer

A useful strategy:

~~~text
             FEWER / SLOWER
             ┌────────────────┐
             │ Load / Soak /  │
             │ Failure tests  │
             ├────────────────┤
             │ Integration    │
             │ + HTTP clients │
             ├────────────────┤
             │ Unit: selector │
             │ / supplier     │
             │ / fallback     │
             └────────────────┘
             MORE / FASTER
~~~

This is a **relative distribution**, not a fixed test-count ratio rule. A team might run dozens of unit tests on every commit, a set of integration tests on every pull request, and heavy load testing before release or on a schedule.

The key point is **not turning every requirement into a `@SpringBootTest`**. If you only need to test `filterByRegion(...)` with three elements, spinning up a full application context adds no meaningful evidence, while making tests slow and sensitive to environment state.

## 4. Unit tests: verifying selection policies as pure functions

### When is a unit test enough?

Suitable scenarios:

- Filtering instances by metadata such as `zone`, `region`, API version, or verified tenant policy.
- Verifying soft fallback or fail-closed behavior.
- Checking how empty lists, missing metadata, or invalid weight values are handled.
- Proving a custom algorithm never selects an element outside the valid set.
- Checking priority/tie-breaking criteria with fixed inputs.
- Verifying request context interpretation when a fake `Request` payload can be constructed.

**Do not spin up an HTTP server in unit tests.** The data source is a list/fake supplier, not real discovery.

### 4.1. Example of a mandatory region-filtering policy

Suppose the system only allows certain instances based on `region`. Extract the filtering logic into an independently testable function:

~~~java
import java.util.List;
import java.util.Objects;
import org.springframework.cloud.client.ServiceInstance;

public final class RequiredRegionPolicy {

    public List<ServiceInstance> eligible(
            List<ServiceInstance> instances,
            String requiredRegion) {

        Objects.requireNonNull(instances);
        Objects.requireNonNull(requiredRegion);

        return instances.stream()
                .filter(instance -> instance.getMetadata() != null)
                .filter(instance -> requiredRegion.equals(
                        instance.getMetadata().get("region")))
                .toList();
    }
}
~~~

This is an **illustrative policy class**. In real usage, a custom `ServiceInstanceListSupplier` can call this same `eligible(...)` function inside `get()`/`get(Request)` to avoid diverging test and production logic.

Unit test using JUnit Jupiter:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.DefaultServiceInstance;

import static org.junit.jupiter.api.Assertions.*;

class RequiredRegionPolicyTest {

    private final RequiredRegionPolicy policy =
            new RequiredRegionPolicy();

    private static ServiceInstance instance(
            String id, String region) {

        DefaultServiceInstance result =
                new DefaultServiceInstance(
                        id, "catalog-service",
                        "127.0.0.1", 8081, false);

        if (region != null) {
            result.getMetadata().put("region", region);
        }

        return result;
    }

    @Test
    void onlyAllowedRegionSurvives() {
        ServiceInstance a = instance("a", "region-a");
        ServiceInstance b = instance("b", "region-b");
        ServiceInstance missing = instance("x", null);

        List<ServiceInstance> actual = policy.eligible(
                List.of(a, b, missing), "region-a");

        assertEquals(List.of(a), actual);
    }

    @Test
    void noAllowedRegionMustFailClosed() {
        ServiceInstance b = instance("b", "region-b");

        assertTrue(policy.eligible(
                List.of(b), "region-a").isEmpty());
    }

    @Test
    void emptyDiscoveryIsStillEmpty() {
        assertTrue(policy.eligible(
                List.of(), "region-a").isEmpty());
    }
}
~~~

The test suite above checks **the resulting list**, not HTTP status codes. If a custom supplier returns an empty list, `RoundRobinLoadBalancer` will have no candidates; how the integration layer represents the specific HTTP error depends on the client/version and should be tested at the integration layer.

### 4.2. Unit testing real suppliers and selectors

If the production class is a custom `ServiceInstanceListSupplier`, test it directly:

- `get()` returns the expected candidate list.
- `get(Request)` receives the required context; hints/tenants are not lost.
- If the delegate returns a `Flux`, test with `StepVerifier` to verify emissions/completion/errors where appropriate.
- Filters rely only on trusted metadata and handle `null` or missing fields.
- No state is retained between requests that lets caller A's data affect caller B.

If testing a custom `ReactorServiceInstanceLoadBalancer`, provide a fake `ObjectProvider<ServiceInstanceListSupplier>` or version-appropriate test fixture and call `choose(request)`. The test should verify that the selected instance is in the allowed set and check the result when the list is empty; there is no need to open sockets.

### 4.3. What not to hard-assert

| Policy | Stable assertion | Flaky-prone assertion |
|---|---|---|
| Round-robin | Every selection belongs to the source set; across enough turns both instances appear in a stable fixture | The first call **always** picks instance A |
| Random | Never picks outside the list; distribution approximates expectation over a large sample | Exactly 50/50 after 10 requests |
| Weighted | In a large statistical test, ratio falls within a justifiable tolerance | Every 4 requests hit A exactly 3 times |
| Zone preference | Returns preferred matches when available; falls back per actual semantics when none match | Never crosses zones when using soft preference |
| Strict region | Never returns a wrong-region instance even if the list becomes empty | Automatically "rescues" requests via disallowed fallback |
| Health check | Filters accurately according to probe snapshot/response | A live instance is always healthy at every moment |

If an algorithm uses a random seed or round-robin state, control the seed/state in the fixture if the API supports it, or assert **invariants** instead of absolute selection order.

## 5. Property testing: property-based checks and boundary tables

Several rules are well suited to property-based testing:

- **Never select outside source:** for any input list, the selector result must belong to that list or be no-server.
- **Fail-closed:** when no instance qualifies, a strict filter must return empty.
- **Do not mutate source:** policies must not perform uncontrolled mutations on shared metadata or lists.
- **Order independence:** if a policy only filters by region, reversing the input list does not change the resulting set.
- **Malformed metadata:** missing `zone`, negative/unparseable `weight`, duplicate instance IDs, and empty lists must not cause unhandled NPEs.

Example test table for a supplier:

| Input | Policy | Expected |
|---|---|---|
| A(zone-a), B(zone-b) | Prefer zone-a | A |
| Only B(zone-b) | Prefer zone-a | B if soft fallback |
| Only B(zone-b) | Require zone-a | Empty if strict |
| A missing zone | Require zone-a | Empty |
| Empty list | Any | Empty / no-server |
| A, A duplicate ID | Select instance | Handles duplicates per contract and policy |
| A weight=0, B weight=3 | Weighted | Verify weight rules for the specific version rather than guessing |

**Unit tests should reflect the actual semantics of the specific supplier.** For example, `ZonePreferenceServiceInstanceListSupplier` and `HealthCheckServiceInstanceListSupplier` have soft fallbacks in common configurations; do not write tests assuming they fail closed by default.

## 6. Integration tests: verifying Spring wiring and real HTTP requests

Unit tests do not detect the following defects:

- Missing `spring-cloud-starter-loadbalancer` dependency.
- `RestClient.Builder` bean lacking `@LoadBalanced`.
- Using a plain `RestClient` bean to call `http://catalog-service`, causing the host to go through DNS.
- `@LoadBalancerClient` specifying the wrong service ID or the configuration class being component-scanned by mistake.
- `SimpleDiscoveryClient` failing to bind URIs from properties.
- LoadBalancer selecting an instance, but HTTP transport failing to connect to the host/port.
- The HTTP client being configured with different retry/timeout values than intended.

To verify these points, you need to **boot a real Spring ApplicationContext** and **one or more test HTTP servers**.

### 6.1. Test dependencies

Example Gradle Kotlin DSL with a compatible Spring Boot/Spring Cloud BOM:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

This snippet assumes the application uses `RestClient` with Java 17+ and Spring Framework 6.1+; depending on the Spring Boot version, the HTTP starter may differ. Select the BOM according to the release train instead of pinning incompatible starter versions.

**You do not need Eureka for every integration test.** When testing Spring Cloud LoadBalancer and HTTP integration specifically, you can use `SimpleDiscoveryClient` with in-process servers. When you want to verify real registration/refresh behavior, expand to Testcontainers + Eureka/Consul or an equivalent test environment.

## 7. Integration test example with two real HTTP backends

The example below uses JDK `HttpServer` as two independent test backends, allocating ephemeral ports to avoid CI conflicts. `@DynamicPropertySource` registers the URIs into `SimpleDiscoveryClient` **before the Spring context is initialized**.

### 7.1. A fairly complete integration test class

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        classes = LoadBalancedRestClientIT.TestApp.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
            "spring.cloud.loadbalancer.cache.enabled=false",
            "spring.cloud.loadbalancer.retry.enabled=false"
        })
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LoadBalancedRestClientIT {

    private static final HttpServer A = server("catalog-a");
    private static final HttpServer B = server("catalog-b");

    @DynamicPropertySource
    static void registerInstances(DynamicPropertyRegistry properties) {
        properties.add(
            "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri",
            () -> "http://127.0.0.1:" + A.getAddress().getPort());

        properties.add(
            "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri",
            () -> "http://127.0.0.1:" + B.getAddress().getPort());
    }

    @Autowired
    @Qualifier("catalogRestClient")
    RestClient client;

    @Test
    void choosesBothInstancesThroughServiceId() {
        Set<String> observed = new HashSet<>();

        for (int i = 0; i < 12; i++) {
            String body = client.get()
                    .uri("/whoami")
                    .retrieve()
                    .body(String.class);
            observed.add(body);
        }

        assertEquals(
                Set.of("catalog-a", "catalog-b"),
                observed);
    }

    @AfterAll
    static void stopServers() {
        A.stop(0);
        B.stop(0);
    }

    private static HttpServer server(String identity) {
        try {
            HttpServer server = HttpServer.create(
                    new InetSocketAddress("127.0.0.1", 0), 0);

            server.createContext("/whoami", exchange -> {
                byte[] bytes =
                        identity.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, bytes.length);

                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            });

            server.start();
            return server;
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {

        @Bean
        @LoadBalanced
        RestClient.Builder loadBalancedRestClientBuilder() {
            return RestClient.builder();
        }

        @Bean("catalogRestClient")
        RestClient catalogRestClient(
                @LoadBalanced RestClient.Builder builder) {
            return builder
                    .baseUrl("http://catalog-service")
                    .build();
        }
    }
}
~~~

**What the test proves:** with LoadBalancer configured under the default round-robin policy, the client calls a service ID URL and receives responses from both physical backends. That is an **integration assertion**, distinct from a unit test that only inspects candidate lists.

**What the test does not prove:** a 50/50 ratio under real load, health-check correctness, retries after timeouts, or stability when a registry dynamically updates the instance list.

### 7.2. Why is it designed this way?

- **Port 0** asks the OS to assign a free port; avoids hardcoding `8081`/`8082` on a shared CI agent.
- **`@DynamicPropertySource`** fits when URIs are only known after the fake servers start.
- **`@DirtiesContext`** prevents reusing a context configured with servers that have already been stopped.
- **Disabling LoadBalancer cache** keeps the example easy to control; in production, caching may need to be enabled.
- **Disabling retry in the test** ensures HTTP call counts are not multiplied by an unintended policy.
- **`RestClient.Builder` with `@LoadBalanced`** enables calling by service ID; if the annotation is omitted and there is no DNS entry for `catalog-service`, the integration test exposes the wiring defect.
- **The assertion uses a result set**, avoiding dependence on which instance is picked on the first request or exact request counts per instance.
- The test uses only in-process servers and does not rely on unstable external services.

The example assumes the test suite has permission to bind loopback ports and that the JDK `jdk.httpserver` module is available. In projects using JPMS or minimal runtime images, ensure this module is present, or substitute WireMock/MockWebServer with compatible managed dependencies.

### 7.3. Ensuring tests do not depend on shared state

If a previous test enabled caching, zone preference, or weighted policies in the same context, observing both instances via round-robin may change. For stability:

1. Explicitly configure properties used by the test.
2. Do not reuse a Spring context holding dynamic URIs from stopped servers.
3. Do not rely on test execution order.
4. Do not share singletons with mutable state across independent test classes without resetting them.
5. Use a fixture tailored to the policy under test rather than adding too many implicit conditions.

## 8. Integration tests for HTTP clients: RestClient, WebClient, and OpenFeign

All three clients can go through Spring Cloud LoadBalancer, but their adapters and observation points differ.

| Client | Integration points to verify | Minimum assertions |
|---|---|---|
| `RestClient` | `@LoadBalanced RestClient.Builder`, `BlockingLoadBalancerClient` | Uses service ID, real server responses |
| `WebClient` | `@LoadBalanced WebClient.Builder` / LoadBalancer exchange filter | `bodyToMono(...)` hits the right instance; cancel/timeout preserves contract |
| OpenFeign | `@FeignClient(name=...)`, `@EnableFeignClients`, `FeignBlockingLoadBalancerClient` | Interface injected, calls service ID, codec/status work |
| HTTP Interface | Proxy backed by LoadBalancer-enabled `RestClient` or `WebClient` | Interface methods reach the right backend; group/auto-config per version |

**Never use a plain HTTP client and assume you have tested LoadBalancer.** A URL like `http://catalog-service` might succeed via Kubernetes/mesh DNS while the application's Spring Cloud LoadBalancer is not involved at all.

### WebClient test

For WebClient, you can use the same fake HTTP servers while declaring a `@LoadBalanced WebClient.Builder`. Assertions should verify:

- Subscription actually executes the request.
- The exchange filter selects the right service ID/instance.
- Valid responses are received when there are no errors.
- Timeouts, cancellations, and body decoding follow WebClient's contract.
- Do not block the event loop with `block()` in reactive production code; in integration tests, synchronization can use `StepVerifier` with a test timeout.

### OpenFeign test

For Feign:

- Verify `@EnableFeignClients` scans the right interfaces.
- Do not set the `url` attribute in `@FeignClient`/properties if you want to test service ID selection; a fixed URL bypasses LoadBalancer.
- Check the actual HTTP `Client` implementation, especially when the project uses Apache HttpClient 5 or overrides `feign.Client`.
- Verify status handling, decoder, connect/read timeouts, request interceptors, and fallbacks separately rather than only checking proxy injection.
- Each test should control retries and idempotency; Spring Cloud OpenFeign typically uses `Retryer.NEVER_RETRY` by default at the Feign layer, which does not mean other layers have disabled retries.

## 9. Important non-happy-path integration scenarios

A test proving only that "200 works" is insufficient. You need a scenario matrix:

| Scenario | Setup | What to verify |
|---|---|---|
| **No instances** | Supplier returns an empty list | No HTTP call sent to another backend; no-server error is handled |
| **Wrong service ID** | `catalog-unknown` has no instances | Does not arbitrarily "fall back" to a physical hostname |
| **Dead instance** | Backend stopped while URI stays in list | Error endpoint may be chosen; transport error is recognized |
| **Discovery update** | Registry/supplier updates the list | After refresh/cache TTL, client stops selecting removed instances |
| **Soft zone preference** | No instance in preferred zone | Falls back per chosen semantics, not treated as a hard constraint |
| **Strict region** | Only forbidden-region instances exist | Zero requests reach forbidden regions; fails closed |
| **Health check** | Health endpoint returns 200/503, changes state | Healthy list updates periodically; fallback when unhealthy is understood |
| **Retry** | First backend returns transient errors | Attempt count, idempotency, and per-attempt instances match policy |
| **Timeout** | Server intentionally responds slowly | Client stops within budget; distinguishes read/connect/pool wait |
| **Contract-breaking response** | Wrong JSON types, HTTP 200 empty body | Decode/validation error raised, not confused with discovery error |
| **Pool saturation** | Concurrent requests hold connections | Bounded wait error when leasing connections; resources are released |
| **Bad instance metadata** | Missing `zone`/`weight` | Policy falls back or rejects as specified |

In integration tests, control backend state via test endpoints, fake registries, or lightweight fault injection. Do not depend on shutting down a production service or altering shared environment firewalls.

### Separating tests with static discovery vs. dynamic registry

`SimpleDiscoveryClient` is well suited for verifying lookup and routing against configured URIs. However, it is a **static instance source**: stopping an HTTP server does not automatically remove it from the list.

To test the **register → deregister → refresh** lifecycle, you need a fixture that supports mutating the list or a real registry in tests. You must also account for DiscoveryClient caches, LoadBalancer caches, health-check intervals, and when the context is initialized.

## 10. Load testing: goals and execution prerequisites

Load testing is not just "sending lots of requests." Before running one, you need **business goals**, **realistic configuration**, and **stop thresholds**.

Common questions include:

- At the **target RPS** and concurrent users, what are p95/p99 latencies?
- Does LoadBalancer produce an appropriate distribution across `ServiceInstance`s?
- Does one instance become a **hotspot** even while other instances remain healthy?
- When a backend slows down, does the connection pool wait queue grow abnormally?
- Do retries multiply request counts and cause a retry storm?
- When an instance is removed, does traffic shift to remaining instances according to policy?
- Under overload, does the system return controlled errors rather than hanging, OOMing, or blocking all callers?

**Load tests must generate traffic at the entry point of the caller using LoadBalancer**, not fire requests directly at individual instances. If the load tool calls `http://127.0.0.1:8081` directly, the results do not measure `order-service`'s instance-selection mechanism.

### Setting a sample test SLO

Example targets specifically for a lab environment:

| Metric | *Illustrative* threshold, not a universal standard |
|---|---|
| Throughput | 60 requests/s at caller entry point |
| End-to-end p95 latency | Under 500 ms |
| End-to-end p99 latency | Under 900 ms |
| HTTP failure rate | Under 1% |
| Load generator missed iterations | 0 dropped iterations |
| Memory/CPU/FD/sockets | Within defined infrastructure limits |
| Instance distribution | Matches algorithm after accounting for filters/weights |
| Retry amplification | Does not exceed agreed attempts/budget limits |

Thresholds must come from **real SLOs and capacity**. Do not pick arbitrary numbers and declare production ready when they pass.

## 11. k6 example: driving load through the caller, not the backend

Suppose `order-service` runs locally on port `8080` with a test endpoint `GET /test/catalog`. This endpoint uses a `@LoadBalanced RestClient` to call `catalog-service` and return the response. This is an **endpoint you must implement for the lab**, not a default Spring Cloud route.

k6 example:

~~~javascript
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    stable_load: {
      executor: "constant-arrival-rate",
      rate: 60,
      timeUnit: "1s",
      duration: "2m",
      preAllocatedVUs: 30,
      maxVUs: 100
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500", "p(99)<900"],
    dropped_iterations: ["count==0"]
  }
};

export default function () {
  const response = http.get(
    "http://127.0.0.1:8080/test/catalog",
    { tags: { operation: "catalog-read" } }
  );

  check(response, {
    "caller returns 200": (r) => r.status === 200
  });
}
~~~

**Measurement explanation:**

- `constant-arrival-rate` attempts to start 60 iterations per second, though this is not guaranteed if VUs or capacity are insufficient.
- `http_req_duration` is the latency **k6 observes from the caller entry point**, not instance-selection time alone.
- `http_req_failed` tracks HTTP request failures from k6 to the caller; downstream failures masked by a 200 response from the application may not be captured by this metric.
- `dropped_iterations` helps detect when the load generator cannot keep up with the scheduled request rate.
- `check(...)` inspects responses; when configuring thresholds, align "business correctness" conditions with failure metrics rather than relying solely on HTTP 200.

**Do not target backend URLs directly** if the goal is to measure LoadBalancer. If running k6 from another container, `127.0.0.1` refers to that container rather than the host; adjust the caller address to match the test topology.

### Distinguishing load tests from stress and soak tests

| Type | Goal | What it concludes |
|---|---|---|
| Baseline | Low, steady traffic | Inherent overhead of components |
| **Load test** | Expected operational traffic | Does it meet SLOs at target load? |
| **Stress test** | Ramp load past limits | Saturation point and failure modes |
| **Spike test** | Sudden surge/drop | Recovery after bursts |
| **Soak test** | Sustained load over time | Leaks in sockets, heap, connection pools, caches/metrics growth |
| **Resilience/failure test** | Kill/slow backend under load | Traffic shifting, retry amplification, and recovery |

These test types can share the same load generator, but **load ramp profiles and acceptance criteria** must be defined separately.

## 12. Measuring the right metrics on both caller and instances

A dashboard showing only "99% success" is rarely enough to explain whether LoadBalancer is performing well.

### Caller layer

Measure:

- Total inbound requests, RPS, p50/p95/p99 latency.
- HTTP statuses and error categories (no-instance, connect/read timeout, 4xx/5xx, decode).
- Instance selection counts by `serviceId` and `instanceId` or permitted safe labels.
- Retry attempts, backoff, and total operation duration.
- Active/pending/idle connections, pool lease time, connect/response time.
- CPU, memory, GC, thread pools, event loops, and file descriptors.
- Cache hits/age and discovery refresh if instrumented.

### Backend layer

Measure:

- RPS and concurrent requests **per instance**.
- Latency and error rate per instance.
- CPU, heap, DB connection pools, queue depth.
- Active HTTP requests, 503/429 responses, and downstream processing time.
- Timestamps when an instance begins/completes graceful shutdown.

You can use Micrometer/Actuator, distributed tracing, structured logs, HTTP client metrics, or `LoadBalancerLifecycle` depending on the system. **Exact metric names and labels depend on versions and configuration**; do not assume every metric appears automatically upon adding a starter.

### Distribution ratios can be misleading

With two equally weighted instances and round-robin, a large enough request volume typically distributes fairly evenly **before retries, filters, or circuit breakers take effect**. Do not draw conclusions from the first few dozen requests because:

- Multiple callers exist, each with its own round-robin state.
- Candidate lists change as health/cache/discovery updates.
- Zone/hint filters may exclude an instance.
- Backends respond at different speeds, skewing completed request counts relative to started requests.
- Retries generate extra attempts.
- Sticky sessions or weighted suppliers skew distribution intentionally.

To evaluate properly, measure both **selection counts** and **actual requests received/completed by backends** over the same time window and policy version.

## 13. Saturation testing: pools, threads, timeouts, and retries

A system can distribute instance selections evenly and still fail due to HTTP transport resources.

Example `RestClient` using Apache HttpClient 5:

~~~text
maxConnTotal = 20
maxConnPerRoute = 8
connectionRequestTimeout = 300 ms
responseTimeout = 2 s
2 catalog-service instances
~~~

If hundreds of concurrent requests hit a route, some requests must **wait to lease a connection** even after LoadBalancer chooses an instance. Other requests connect successfully, but a slow backend triggers a **response timeout**.

These represent distinct root causes:

| Observation | Likely bottleneck | Required evidence |
|---|---|---|
| High pool pending, leased hits max per-route | Per-route limit | Connection manager route stats |
| Total leased hits total max, multiple routes pending | Global pool limit | Total pool stats |
| Pool has capacity, response timeouts rise | Slow backend/proxy | Server processing duration, traces |
| Error rate rises after enabling retries | Retry amplification | Attempts per operation, queues, backend RPS |
| No-instance errors rise | Discovery/health/policy | Supplier candidates and LoadBalancer selections |

Load testing is useful when **measuring caller, HTTP pool, and backend simultaneously**. Measuring only p95 from the load generator tells you the system is slow, not which stage is slow.

### Enabling retries can turn a small error into a traffic storm

Suppose 100 operations/s each fail and retry twice. The system can generate up to roughly 300 attempts/s when every attempt reaches the backend without being capped at another layer. This is an illustrative model, not a universal upper bound in systems with multiple retry layers.

During load tests, record:

- Operations count vs. actual HTTP attempts.
- Retries per operation.
- Ratio of retries on the same instance vs. another instance.
- Backoff/jitter and overall deadline.
- Load increase on healthy backends when one instance stops serving.

**Never blindly retry non-idempotent operations** such as order creation or payment without duplicate-write protection.

## 14. Testing under instance removal

Realistic scenario: `catalog-a` and `catalog-b` are running; under load, instance A is stopped.

Clarify differences between mechanisms beforehand:

1. **Dynamic discovery:** an instance may be removed after a heartbeat/refresh interval.
2. **LoadBalancer cache:** stale data can persist until refresh/TTL.
3. **Health-check supplier:** runs on its own probe schedule and may fall back to the full source when none are healthy.
4. **HTTP transport pool:** may retain idle sockets to the stopped instance.
5. **Retry:** may re-select the same or next instance depending on policy.
6. **Strict routing:** must not bypass region/tenant restrictions just to make a request succeed.

### Steps for resilience testing under load

- Run a steady load test and record the baseline.
- Stop instance A in the test environment or apply fault injection.
- Record when A stops serving, when discovery removes A, and when LoadBalancer stops picking A.
- Measure error rate, latency tail, retry count, and load on B during the transition window.
- Restart A and measure re-registration time and recovery capability.
- Verify the system does not trigger a retry storm, exhaust pools, or call policy-forbidden instances.

**Do not claim that stopping a server under static `SimpleDiscoveryClient` causes the instance list to update automatically.** To test discovery lifecycles, use a mutable source or dynamic registry, not just closing a port.

## 15. Matrix: which test belongs where?

| Case to prove | Unit | Integration | Load |
|---|:---:|:---:|:---:|
| Region filter works on sample list | **Primary** | Smoke/confirm bean wiring | Not needed |
| Soft zone fallback on no match | **Primary** | Can verify real URI | Only to measure cross-zone traffic |
| Empty instance list → no-server | **Primary** | **Required** to inspect adapter/client error representation | Monitor error spikes during discovery outages |
| `@LoadBalanced RestClient.Builder` actually wired | No | **Primary** | Measure only after wiring PASSES |
| `@FeignClient` scanned and decoder works | No | **Primary** | Depends on load/protocol |
| Connect/read timeouts configured properly | Can test settings logic | **Primary** with fake slow backend | **Primary** when backend slows under load |
| Retries stay within attempt limit | **Primary** | **Primary** with fake errors | **Primary** to measure amplification |
| Pool sizing and queueing under high concurrency | Insufficient | Small boundary test | **Primary** |
| Round-robin distributes relatively evenly under load | Can verify algorithm | A few requests to confirm multi-instance | **Primary** for real workload validation |
| Weighted 3:1 | Test weight policy | Selects right candidate | **Primary** for ratio under load |
| Instance stopped/restarted | Unit for empty/fallback | **Primary** for HTTP/failover | **Primary** for recovery SLO |
| No token leaks in logs | Unit for log formatter | **Primary** with canary | Check log capture under load if needed |
| JSON contract/error status | Unit DTO validation | **Primary** | Secondary, does not replace contract tests |
| p95/p99, throughput, and CPU | No | Insufficient | **Primary** |

"Primary" denotes the layer providing the strongest evidence. An important requirement typically has **a thorough group of unit tests** plus **a few representative integration tests**, rather than repeating the full Cartesian product at every layer.

## 16. How to reduce flaky tests in CI

LoadBalancer tests easily become unstable when they accidentally depend on timing and shared resources.

### Unit tests

- Use immutable candidate lists; avoid sharing state across tests.
- Do not assert initial round-robin selection order unless state is reset/seeded.
- For random/weighted policies, use invariant tests or acceptance bands with enough samples; avoid checking ratios over 5 requests.
- Do not depend on the system clock unless using a test-controlled clock/scheduler.

### Integration tests

- Use ephemeral ports rather than fixed ports that conflict easily.
- Use `@DynamicPropertySource` or appropriate test configuration instead of hardcoding unreachable URIs.
- Ensure servers start before Spring resolves properties.
- Close servers, request factories, and connection pools after tests to prevent thread leaks.
- Control caching, health schedulers, retries, and context caching.
- Avoid `Thread.sleep` to wait for discovery/health updates; prefer polling with explicit timeouts and check conditions.
- For reactive code, use `StepVerifier` and virtual time when testing virtualizable timing logic; real networking still depends on wall-clock time.
- Do not share random ports/context caches when another test class uses the same configuration but its servers have stopped.

### Load tests

- Ensure the load generator is not the first bottleneck.
- Do not run multiple heavy benchmarks in parallel on the same resource-constrained CI worker without isolation.
- Warm up JIT, connection pools, and caches before taking official measurements if the test requires it.
- Keep server/client configs, datasets, instance counts, and versions identical when comparing before/after.
- Run multiple trials to distinguish infrastructure noise from regressions.
- Do not treat a short benchmark run as accurate evidence for p99 under low traffic.
- Use an isolated test environment; do not send destructive load to production or shared systems.

## 17. Structuring CI/CD pipelines by cost and risk

You can structure it as:

~~~mermaid
flowchart TD
    A["Developer push / pull request"]
    B["Unit tests<br/>policy, supplier, selector"]
    C{"PASS?"}
    D["Integration tests<br/>Boot context + fake HTTP servers"]
    E{"PASS?"}
    F["Build artifact / candidate"]
    G["Load baseline + regression test<br/>isolated environment"]
    H{"SLO & policy PASS?"}
    I["Allow release per process"]
    X["Stop pipeline and report failure"]
    A --> B --> C
    C -->|"No"| X
    C -->|"Yes"| D --> E
    E -->|"No"| X
    E -->|"Yes"| F --> G --> H
    H -->|"No"| X
    H -->|"Yes"| I
~~~

Not every organization runs a **full load test** on every pull request. You can use:

- **Every commit/PR:** unit suite + core integration tests, fail fast.
- **Before merge/release:** full integration tests, HTTP contracts, small performance smoke test.
- **Before major releases or on a schedule:** load/stress/soak/failure tests in a production-like environment.
- **Post-release:** canary metrics, alerts, and fast rollback capability if distribution/errors/latency drift from expectations.

Store test configurations alongside application versions so regressions can be explained: Spring Cloud dependencies, HTTP transport, cache TTL, retry policy, server capacity, and discovery data can all influence results.

## 18. Acceptance checklist and what not to infer

Before considering load balancing sufficiently tested, answer:

1. **Unit:** does every key policy have tests for empty lists, missing metadata, fallbacks, and forbidden items?
2. **Unit:** does any custom selector have tests proving it never picks outside the candidate set?
3. **Integration:** are `@LoadBalanced` beans verified and is the service ID resolved via LoadBalancer rather than DNS?
4. **Integration:** have at least two test backends been called and their returned instance IDs verified?
5. **Integration:** are 4xx/5xx responses, empty discovery, timeouts, and decode errors classified properly?
6. **Integration:** do retry/health/cache have tests modeling their lifecycle and timing accurately?
7. **Load:** is traffic sent **to the caller** rather than bypassing LoadBalancer?
8. **Load:** are both caller and per-instance metrics, pools, CPU, latency tail, and attempts measured?
9. **Load:** are clear SLOs/acceptance thresholds and abort conditions defined?
10. **Load:** has a slow or stopped instance been tested under load?
11. **Isolation:** do tests use dedicated ports, mock data, and avoid mutating shared environments?
12. **Observability:** do traces/metrics/logs explain failures without logging tokens, cookies, or sensitive data?
13. **CI/CD:** do fast tests run frequently while heavy tests run at an appropriate risk/cadence?
14. **Reporting:** are results saved with versions/configs and do they explicitly state what has not been proved?

**Conclusion:** Use **unit tests** to prove the correctness of policies, suppliers, and selectors; **integration tests** to prove Spring Cloud LoadBalancer is genuinely wired into `RestClient`, `WebClient`, or OpenFeign and HTTP requests reach the right `ServiceInstance`; and finally **load testing** to evaluate distribution, p95/p99, pool saturation, retry amplification, and recovery. These three testing layers complement one another: **correct logic does not imply correct wiring; correct wiring does not imply resilience under load**.

**Official references:**

- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons – RestClient as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Framework – Dynamic Property Sources in integration tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Framework – TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html)
- [Grafana k6 – Constant arrival rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/)

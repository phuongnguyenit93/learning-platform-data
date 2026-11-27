# Test Actuator endpoints in Spring Boot

Spring Boot Actuator provides operational endpoints such as `health`, `info`, `metrics`, and `prometheus`. These endpoints are the interfaces that Kubernetes, load balancers, monitoring platforms, and operations teams use to inspect application state. Just because an endpoint exists in an application does not mean it is exposed, properly secured, or returning the right status code in every situation. **Testing Actuator endpoints** verifies response payloads, HTTP semantics, exposure, security, health contributors, and compatibility with the deployment environment.

In the **SPRING_BOOT_OBSERVABILITY** module, testing Actuator is part of testing observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. This lesson belongs to the **Testing observability** chapter and focuses on how to test Actuator endpoints: test slices vs. full application context, MockMvc/WebTestClient, health groups, custom indicators, status aggregation, security, metrics/Prometheus, endpoint exposure, and production-like smoke tests.

## Learning objectives

1. Distinguish between an endpoint being enabled, exposed, and authorized.
2. Choose an appropriate Spring Boot test slice or full context.
3. Test health status, contributors, groups, and HTTP status mapping.
4. Test security, component details, and endpoint exposure.
5. Test metrics and Prometheus scrape output.
6. Use mock/fake dependencies to produce deterministic health states.
7. Verify management port, base path, and profile-based configuration.
8. Design smoke tests in containers/Kubernetes.
9. Avoid flaky tests caused by real dependencies, timing, and environment state.

## 1. What to test on Actuator

An Actuator endpoint has multiple behavioral layers:

- Endpoint implementation: the data or actions the endpoint returns.
- Enablement: whether the endpoint is enabled in the application context.
- Exposure: whether the endpoint is exposed over HTTP/JMX.
- Security: which callers are permitted access and details visibility.
- HTTP semantics: status code, content type, and response body.
- Runtime integration: contributors, registries, exporters, and management server.
- Deployment integration: port, base path, network policy, and probe configuration.

A test that only checks the JSON body can miss a mis-exposed endpoint or a security chain allowing unauthorized access.

### 1.1. Enable, expose, and authorize

| Concept | Question | Configuration/check |
| --- | --- | --- |
| Enable | Is the endpoint bean created? | Endpoint availability/configuration |
| Expose | Is the endpoint reachable over HTTP/JMX? | `management.endpoints.*.exposure` |
| Authorize | Which callers may access it? | Spring Security |
| Details | May the caller see component details? | `show-details`/`show-components` |
| Network | Can kubelet/monitoring reach the port? | Service, port, NetworkPolicy |

For example, the `health` endpoint may be enabled by default and exposed over HTTP, while `metrics` or `env` are not exposed. Do not infer exposure simply because an endpoint class is on the classpath.

## 2. Test dependencies and basic configuration

Add test dependencies via the Spring Boot BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

For reactive applications, use `WebTestClient` and its corresponding test dependencies. Do not pin separate versions when managed by the BOM.

Production configuration might expose `health`, `info`, and `prometheus`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: never
~~~

Tests should use explicit configuration independent of production secrets. Do not broaden exposure in tests and then assume production is also safe.

### 2.1. Test profiles

You can set test properties for management endpoints:

~~~java
@SpringBootTest(properties = {
    "management.endpoints.web.exposure.include=health,metrics,prometheus",
    "management.endpoint.health.show-details=always"
})
~~~

Only use `show-details=always` in a test context with non-sensitive fixtures. Separate security tests must verify that production policy does not allow anonymous callers to view details.

## 3. Choosing a test style: slice vs. full context

| Test style | Scope | When appropriate |
| --- | --- | --- |
| Unit test | A single `HealthIndicator`/isolated logic | Checking status mapping, timeouts/errors |
| `@WebMvcTest` | MVC/security slice | Testing controller/security behavior when Actuator endpoints are imported appropriately |
| `@SpringBootTest` + `MockMvc` | Full application context, mock servlet requests | Testing Actuator auto-configuration and endpoint exposure |
| `@SpringBootTest` + `RANDOM_PORT` | Real embedded server | Testing HTTP server, management port, and filters |
| `WebTestClient` | Reactive or HTTP client test | WebFlux and end-to-end HTTP checks |
| Container/Kubernetes smoke test | Runtime image/cluster | Verifying port, path, network, and probes |

With Actuator auto-configuration, a full context is usually the clearest choice for integration tests. Slice tests may fail to load endpoint infrastructure or required auto-configuration if configuration is narrowed.

## 4. Testing the health endpoint with MockMvc

Example integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health",
        "management.endpoint.health.show-details=never"
})
@AutoConfigureMockMvc
class ActuatorHealthEndpointTest {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsUpStatus() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
~~~

This test verifies that the endpoint is exposed and returns status `UP` in the test context. If the context contains a real database or dependency, results can depend on the environment. Use a test database or replace dependencies with fakes for deterministic results.

### 4.1. Checking content type and response contract

When clients/monitoring depend on response shape, verify content type and required contract fields. Avoid asserting the entire JSON if responses include contributors that vary by classpath. Assert stable fields such as `status` and mandatory components.

### 4.2. Testing when health is DOWN

Do not force the entire application context into an error state just to test one contributor. Replace the dependency with a fake returning failure, call the endpoint, and verify body/status code per aggregation policy. Health `DOWN` usually maps to HTTP 503, though custom status mappings can alter this.

## 5. Testing a custom HealthIndicator

Unit testing a contributor independently:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;

import static org.assertj.core.api.Assertions.assertThat;

class SearchHealthIndicatorTest {

    @Test
    void reportsDownWhenSearchIsUnavailable() {
        SearchClient client = () -> false;
        SearchHealthIndicator indicator = new SearchHealthIndicator(client);

        assertThat(indicator.health().getStatus()).isEqualTo(Status.DOWN);
    }
}
~~~

The example assumes `SearchClient` has a `ping` method returning boolean. Unit tests should cover:
- dependency returning success;
- dependency returning failure;
- timeout;
- exception;
- malformed response if applicable;
- details containing no secrets.

### 5.1. Using fakes instead of real dependencies

Fakes let tests control state without a database/broker/search cluster. For instance, a fake client can flip from available to unavailable. Avoid calling external services in unit tests because network and environment state make tests unstable.

### 5.2. Checking timeouts

A `HealthIndicator` needs a finite timeout. Use a delayed fake client or test clock to verify timeout mapping. Never use arbitrarily long `Thread.sleep` calls; if there is no clock abstraction, use a short timeout with a reasonable upper bound and clean up the executor.

## 6. Health groups: liveness and readiness

When Kubernetes probes are enabled, Spring Boot can expose:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Test each group separately. A database failure may mark readiness `DOWN` if the database is a mandatory dependency, whereas liveness should stay `UP` if the process can still run.

~~~java
@SpringBootTest(properties = {
    "management.endpoint.health.probes.enabled=true",
    "management.endpoints.web.exposure.include=health"
})
@AutoConfigureMockMvc
class ActuatorProbeGroupsTest {
    @Autowired
    MockMvc mvc;

    @Test
    void livenessEndpointIsAvailable() throws Exception {
        mvc.perform(get("/actuator/health/liveness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }

    @Test
    void readinessEndpointIsAvailable() throws Exception {
        mvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk());
    }
}
~~~

If the application has a startup coordinator keeping readiness in `REFUSING_TRAFFIC`, tests must trigger or wait for warm-up completion per contract. Do not assume readiness is always `UP` immediately when the test context starts.

### 6.1. Verifying group membership

Create a custom indicator included only in the readiness group. Make it return `DOWN` and verify readiness is affected while liveness stays `UP`. This test catches configurations where liveness accidentally depends on external services.

### 6.2. Verifying status mapping

Verify:
- `UP` returns HTTP success;
- `DOWN` returns HTTP failure per mapping;
- `OUT_OF_SERVICE` is handled per policy;
- custom statuses have configured mappings;
- callers reading status do not require component details if that is the probe contract.

## 7. Testing security and component details

Actuator endpoints can reveal database names, internal hosts, disk paths, or exception details. Security tests must verify both access permissions and returned data.

Illustrative security filter chain example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ActuatorSecurityConfiguration {
    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/actuator/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health").permitAll()
                        .anyRequest().hasRole("OPS"))
                .httpBasic()
                .and()
                .build();
    }
}
~~~

Security DSL syntax can differ across Spring Security versions; use the API matching your dependency version. Applications with multiple filter chains should set `@Order` so the management chain does not accidentally intercept business routes.

### 7.1. Anonymous callers

Test unauthenticated callers:
- minimal health status is accessible if probe policy allows;
- `metrics`/`prometheus` and other management endpoints are denied if policy requires;
- component details do not appear.

### 7.2. Authorized callers

Use Spring Security test support to authenticate a user with the `OPS` role and verify endpoints/details per policy. Also test an authenticated user lacking the role so authentication is not confused with authorization.

### 7.3. Details policy

Configure `show-details=when-authorized` and `show-components=when-authorized` when only authorized users should view details. Verify anonymous responses contain no `components`/`details` and authorized responses include only approved fields.

Do not check only HTTP 200/403; inspect the JSON body to ensure no hosts, URLs, credentials, or exception messages leak.

## 8. Testing endpoint exposure

Exposing endpoints over HTTP is configured separately:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Test that exposed endpoints return expected responses and unexposed endpoints return 404 per framework behavior/version. Also test profile configurations if production uses profile-specific exposure.

### 8.1. Negative exposure tests

For example, the `env` endpoint is not in the include list. Send a request to `/actuator/env` and verify it cannot be accessed over the web. If blocked by security rather than unexposed, the status code may differ; the goal is proving callers cannot retrieve data.

### 8.2. JMX and HTTP

HTTP exposure does not imply JMX exposure. If the system uses JMX, test JMX endpoint exposure and authentication/network policy separately. Do not skip JMX just because HTTP endpoints are secured.

## 9. Testing metrics and the Prometheus endpoint

The metrics endpoint lists meter names and reads specific meters. The Prometheus endpoint outputs scrape format.

Example configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Integration tests can verify:
- `/actuator/metrics` returns the meter list;
- required meters exist in the registry;
- `/actuator/metrics/{name}` returns measurements;
- `/actuator/prometheus` returns the expected content type/format;
- meter names and tags contain no dynamic IDs.

### 9.1. Testing registered meters

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class MetricsRegistryTest {
    @Autowired
    MeterRegistry registry;

    @Test
    void registersJvmMemoryMetric() {
        assertThat(registry.find("jvm.memory.used").meter()).isNotNull();
    }
}
~~~

Meter names depend on the registry and binders. Use names verified in the actual application; tests should not depend on meters absent from the dependency set.

### 9.2. Testing Prometheus scrape

Use MockMvc or an HTTP client to call `/actuator/prometheus` and verify the response contains an expected registered stable metric. Avoid asserting the entire output because JVM/process metrics vary across environments and versions.

### 9.3. Cardinality regression tests

You can send multiple requests with different user/order IDs and verify that the number of meter time series does not grow with those IDs. Metric tag names/values should be allow-listed and reviewed.

## 10. Management port and real HTTP tests

MockMvc does not verify network listeners or a separate management server port. If `management.server.port` differs from the application port, use `RANDOM_PORT` or a container smoke test to confirm management endpoints actually listen on the expected port.

Example server test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "management.server.port=0"
)
class ManagementPortTest {
    @LocalManagementPort
    int managementPort;

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void healthIsServedOnManagementPort() {
        ResponseEntity<String> response = restTemplate.getForEntity(
                "http://localhost:" + managementPort + "/actuator/health",
                String.class);

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
    }
}
~~~

Test annotations and management port support depend on Spring Boot version. If not using a separate management port, tests can use the local server port and exact base path.

### 10.1. Testing base path

If `management.endpoints.web.base-path` changes from `/actuator` to `/manage`, verify the old path is no longer exposed and the new path returns responses. This prevents manifests/probes from pointing to the old endpoint.

## 11. WebTestClient for reactive applications

With WebFlux, `WebTestClient` can test HTTP endpoints and reactive responses. When testing an application context without opening a server, bind `WebTestClient` using your Spring Boot version's test support. With `RANDOM_PORT`, the client sends requests through the embedded server to verify filters and networking.

Reactive `HealthIndicator` tests must verify the publisher completes/errors within a timeout. Never block the event loop in indicators or test paths.

## 12. Keeping health endpoint tests stable and environment-independent

A common cause of flaky tests is an auto-configured indicator calling a real database/broker. When a developer has the service running locally while CI does not, test behavior diverges.

Strategies:
- use a test database/container when integration verification is needed;
- fake dependencies for status aggregation tests;
- disable unrelated contributors in test profiles when appropriate;
- avoid relying on external public endpoints;
- fix clocks/configuration when testing caches/TTLs;
- set explicit timeouts and cleanup;
- avoid asserting exact latency in milliseconds.

If a test needs to prove DataSource health, use Testcontainers or a managed test database service. If it only needs to prove endpoint aggregation, a fake contributor suffices.

## 13. Troubleshooting Actuator endpoint tests

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Endpoint returns 404 | Not exposed or wrong base path | Check exposure/path |
| Endpoint returns 401/403 | Blocked by security chain | Check matchers, roles, and test user |
| Health returns `DOWN` in CI | Contributor depends on external service | Fake dependency or test container |
| MockMvc cannot find endpoint | Slice test missing Actuator auto-config | Use full context or import proper config |
| Health body `UP` but HTTP 503 | Status mapping/customizer | Check HTTP mapping and contributors |
| Readiness `DOWN` in test | Warm-up not finished | Trigger/await readiness transition |
| Details leaked to anonymous | Wrong `show-details`/security policy | Test response body and authorization |
| Prometheus endpoint empty | Registry/exporter has no meters | Check dependencies/binders/registry |
| Meter name differs from expected | Different registry/version | Inspect registry at runtime |
| Management port test fails | Wrong port/path/context setup | Use `@LocalManagementPort` and `RANDOM_PORT` |
| Test times out | Health indicator blocks or retries | Dependency timeout and bounded tests |
| Passes locally but fails in CI | Environment dependency | Fakes/containers and deterministic fixtures |

### 13.1. Investigation workflow

1. Identify whether the test is a slice or full application context.
2. Check Actuator dependencies, endpoint enablement, and HTTP exposure.
3. Verify base path, management port, and active profile.
4. Read response status/body to distinguish health failure from security failure.
5. Inspect health contributors and external dependencies.
6. Check security chain order, matchers, and test principal.
7. Verify `MeterRegistry`/exporter and actual meter names.
8. Run container/cluster smoke tests if failures occur only after deployment.

## 14. Production-like smoke tests and CI

Unit/integration tests do not prove deployment manifests, container ports, or NetworkPolicies work. CI/CD should have layers:

1. Unit tests for custom indicators and health logic.
2. Application integration tests for Actuator configuration.
3. Security tests for anonymous/authorized callers.
4. Container smoke tests for image and management port.
5. Manifest validation for probe paths/ports.
6. Staging smoke tests from a network perspective similar to kubelet/monitoring.
7. Post-deploy verification for health, metrics scrape, and alert pipelines.

Never run destructive smoke tests against production. Use read-only endpoints and synthetic fixtures with cleanup.

### 14.1. Post-deploy readiness checks

After rollout, verify:
- expected replicas are all Ready;
- readiness path returns the appropriate status;
- liveness path does not depend on database outages;
- Prometheus targets are scraped;
- management endpoints are not unintentionally public;
- logs/alerts do not report abnormal endpoint failures.

### 14.2. Contract tests

If monitoring platforms depend on metric names or health response fields, maintain contract tests for those stable parts. When upgrading Spring Boot/Micrometer, run contract tests to catch changes in naming, content type, or endpoint behavior.

## 15. Production checklist

| Criterion | Evidence |
| --- | --- |
| Clear endpoint enable/exposure | Positive and negative exposure tests |
| Health status contract | `UP`/`DOWN` and HTTP mapping |
| Health groups | Liveness/readiness membership |
| Custom indicators | Success/failure/timeout/exception |
| Security | Anonymous, authorized, and unauthorized tests |
| Details privacy | No leaked internal data |
| Metrics registry | Verified meter names/tags |
| Prometheus scrape | Format/content type and metric presence |
| Cardinality | IDs do not create new time series |
| Management port/base path | Real HTTP test |
| Runtime image | Container smoke test |
| Kubernetes manifest | Probe path/port validation |
| CI determinism | No dependency on external services outside test |
| Upgrade safety | Contract tests across version changes |

## 16. Practice: building an Actuator test suite for order-service

**Scenario:** `order-service` exposes health, readiness/liveness, metrics, and Prometheus. CI occasionally fails because the test database is unavailable; the health details endpoint once accidentally leaked a hostname in staging.

**Tasks:**

1. Create a full-context integration test for `/actuator/health`.
2. Use fake database/search indicators to test `UP`/`DOWN` aggregation.
3. Test readiness and liveness groups independently.
4. Test status-to-HTTP mapping for `DOWN` and `OUT_OF_SERVICE`.
5. Test that anonymous callers see only minimal status.
6. Test that the `OPS` role sees approved details.
7. Test that unexposed endpoints like `env`/`configprops` are unreachable.
8. Test that `MeterRegistry` has required meters and tags exclude order/customer IDs.
9. Test Prometheus scrape output with a stable metric.
10. Test the separate management port and base path.
11. Build the container and run a smoke test from a deployment-like network context.
12. Write CI stages and runbooks for 404, 503, 401/403, missing metrics, and probe failures.

**Expected outcome:** a test suite covering endpoints, security, health groups, metrics, management port, container smoke tests, and contract verification.

## 17. Key takeaways

Testing Actuator endpoints must verify enablement, HTTP exposure, authorization, response contracts, and runtime connectivity. Unit testing a custom `HealthIndicator` does not prove the endpoint is exposed; MockMvc does not prove the management port or NetworkPolicy works; container smoke tests add evidence from a production-like runtime.

Use fake contributors for aggregation tests and test containers when verifying real dependencies. Test liveness/readiness, status mapping, security/details, metrics registry, and Prometheus output separately. Keep tests deterministic, avoid external service dependencies, and avoid asserting full responses containing classpath-dependent fields. When deploying, verify probe paths/ports and monitoring scrapes. Metrics, logs, and traces aid diagnostics; endpoint tests ensure those operational interfaces work properly and do not leak data.

**References:**
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Health Endpoint](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/)
- [Micrometer — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Testcontainers — Spring Boot](https://java.testcontainers.org/modules/databases/)

# Missing Metrics or Health Indicator Due to Missing Dependencies or Exposure

When deploying Spring Cloud CircuitBreaker with Resilience4j, the application may call dependencies and transition breaker states normally, yet neither metrics nor health indicators appear in Spring Boot Actuator. These two capabilities require separate integration components: Actuator provides endpoints, Micrometer collects and exports metrics, and Resilience4j needs an appropriate binder or Spring Boot integration to register meters and health contributors.

A missing endpoint is not enough to conclude the circuit breaker is broken. A dependency might be missing, versions mismatched, the registry missing, per-instance health indicator registration disabled, or the endpoint might exist without HTTP exposure. Inspect each layer in order to pinpoint the true cause.

## 1. Distinguish Metrics, Health Indicators, and Circuit Breaker State

These three concepts are related yet answer different questions:

| Component | Purpose | Where Usually Observed |
| --- | --- | --- |
| Circuit breaker runtime | Permits or rejects calls based on state and sliding window | `CircuitBreakerRegistry`, logs, and events |
| Micrometer metrics | Counts outcomes, measures durations, failure/slow rates, and states | Actuator `/metrics`, Prometheus, or metrics backend |
| Health indicator | Summarizes breaker condition into a health contributor | Actuator `/health` and health groups |

The breaker can operate even without a metrics binder added. Metrics can exist inside `MeterRegistry` even if `/actuator/metrics` is not exposed. The health endpoint can return `UP` without breaker details if the integration or health indicator registration setting is not enabled.

Therefore, clarify the exact symptom:

- No `/actuator/metrics` or `/actuator/prometheus` endpoint.
- Endpoint exists, yet Resilience4j meters are not listed.
- Meters exist, yet have no data or lack tags for the breaker ID.
- `/actuator/health` works, yet shows no circuit breaker component.
- Health component exists, yet fails to reflect state or overall status differs from expectations.

Each case has a different cause and verification path.

## 2. Check Dependencies First

With Maven, an application using Spring Cloud CircuitBreaker's Resilience4j backend typically needs the corresponding starter, Actuator, and Micrometer binder. If scraping via Prometheus, add the Prometheus registry as well:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-micrometer</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
```

Role of each dependency:

- `spring-cloud-starter-circuitbreaker-resilience4j` provides the Spring Cloud CircuitBreaker factory backed by Resilience4j.
- `spring-boot-starter-actuator` provides operational endpoints such as health and metrics.
- `resilience4j-micrometer` provides meter bindings for Resilience4j components.
- `micrometer-registry-prometheus` provides the Prometheus registry and scrape format.

If the application needs Resilience4j's automatic Spring Boot health indicator, check that the project uses the integration compatible with your Spring Boot version. For Spring Boot 3, the usual artifact is `resilience4j-spring-boot3`; Spring Boot 2 projects need the Boot 2 artifact. The Spring Cloud factory integration and native Spring Boot integration serve different purposes; avoid adding multiple starters blindly if they create duplicate configurations or registries. Verify which beans and registries the application actually uses.

Manage Spring Boot, Spring Cloud, Resilience4j, and Micrometer versions through a compatible BOM or dependency management. Avoid mixing versions from different release trains, as auto-configuration or meter binders may be incompatible.

### Check the Dependency Tree

With Maven Wrapper, inspect the dependency tree to confirm artifacts are on the runtime classpath:

```bash
./mvnw dependency:tree
```

You can filter by the relevant groups:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.cloud,io.github.resilience4j,io.micrometer
```

Check dependency scopes as well. A library scoped only to `test` will not be loaded in production runtime. If using Gradle, inspect `runtimeClasspath` rather than only compile/test configurations.

## 3. Enable Proper Actuator Endpoint Exposure

Having the Actuator dependency does not mean every endpoint is open over HTTP. Spring Boot separates whether an endpoint is enabled from whether it is exposed over web or JMX. Example configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
```

`health` is usually exposed by default in standard setups, whereas `metrics` and `prometheus` must be included in the exposure list to be reachable over HTTP. `prometheus` works only when the Prometheus registry is on the classpath and auto-configured.

If the application configures `management.endpoints.web.exposure.include` across multiple profile files, check the final merged value. A profile file might override the exposure list and accidentally drop `metrics` or `prometheus`.

Exposure is no substitute for security. Expose only necessary endpoints, restrict access to monitoring/management networks, and enforce proper authentication/authorization. Never publicly expose `env`, `configprops`, or sensitive health details just for diagnostics.

## 4. Verify Endpoints Are Actually Exposed

Once the application starts, query using the right host, port, and management base path:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/prometheus
```

If using a dedicated management port, custom context path, or reverse proxy, URLs change accordingly. Example:

```yaml
management:
  server:
    port: 9091
  endpoints:
    web:
      base-path: /manage
```

In that case, the endpoint may be `http://localhost:9091/manage/health`, not `/actuator/health` on the application port. Check actual configuration rather than guessing URLs.

Interpret HTTP statuses and responses:

| Result | What to Check |
| --- | --- |
| `404 Not Found` | Endpoint is not exposed, wrong base path/port, or endpoint is not auto-configured |
| `401 Unauthorized` / `403 Forbidden` | Endpoint likely exists, but is blocked by Spring Security or a proxy |
| `503 Service Unavailable` on health | A health contributor reports `DOWN` or overall status failed; inspect details if authorized |
| `200 OK` without breaker details | Health endpoint works, but Resilience4j's health contributor may not be registered or enabled |
| `/metrics` exists without Resilience4j meters | Check Micrometer binder, registry, and whether the breaker has been created/registered |
| `/prometheus` returns `404` | Check Prometheus registry dependency and exposure |

If an endpoint is blocked by security, do not disable all security to test. Use an authorized management account/role or test from the monitoring network per application policy.

## 5. Enable Resilience4j's Health Indicator

With Resilience4j's Spring Boot integration, enable the health indicator globally and register indicators for the instances you want to monitor. Example:

```yaml
management:
  health:
    circuitbreakers:
      enabled: true
  endpoint:
    health:
      show-details: when_authorized

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
```

The two settings serve distinct roles:

- `management.health.circuitbreakers.enabled` enables the circuit breaker health contributor in the corresponding Actuator integration.
- `resilience4j.circuitbreaker.instances.inventory.registerHealthIndicator` requests registering a health indicator for the `inventory` instance.

The exact name and capabilities of the health contributor depend on the Resilience4j Spring Boot integration version. After enabling, call `/actuator/health` to see the actual component list; if components are exposed individually, use the exact ID returned in the response. Do not assume every version uses the same sub-path convention.

If the application uses only the Spring Cloud CircuitBreaker factory without the Spring Boot health integration, the factory can work normally while Resilience4j's native health contributor does not appear automatically. When a health indicator is needed, add the compatible integration or implement a custom `HealthIndicator` backed by the exact breaker instance the application uses.

## 6. Health Indicator Is Not the Same as Readiness and Liveness

A circuit breaker health indicator may report `DOWN` when the breaker is `OPEN`, depending on the integration and version's mapping. That reflects an unhealthy dependency from the caller's perspective; it does not necessarily mean the Spring Boot process is dead or incapable of serving any requests.

In Kubernetes, distinguish between:

- **Liveness:** whether the process is alive and can continue running.
- **Readiness:** whether the instance should receive new traffic.
- **Dependency health:** whether a specific downstream service can currently serve calls.

Do not arbitrarily put dependency health indicators into the liveness probe. If Inventory Service suffers an outage, the breaker transitions to `OPEN`, overall health turns `DOWN`, and the liveness probe causes Kubernetes to restart all Order Service pods, the system can enter a restart loop even though the application could still serve other features or return fallbacks.

Design health groups cleanly. Liveness should reflect process health; readiness can reflect serving capability per service policy; dependency health should be tracked separately or included in readiness only when business requirements truly demand it. Be cautious about marking every replica not-ready simultaneously due to a single shared dependency failing.

## 7. Check the Micrometer Binder and Meter Registry

Once Actuator `/metrics` is available, inspect the list of meters:

```bash
curl http://localhost:8080/actuator/metrics
```

Look for Resilience4j-related meters, typically named like:

- `resilience4j.circuitbreaker.calls`
- `resilience4j.circuitbreaker.state`
- `resilience4j.circuitbreaker.failure.rate`
- `resilience4j.circuitbreaker.slow.call.rate`
- `resilience4j.circuitbreaker.buffered.calls`

Exact names and tags can vary by version and registry. Use the meter list returned by the running application as the source of truth. Once a meter appears, query a specific meter:

```bash
curl "http://localhost:8080/actuator/metrics/resilience4j.circuitbreaker.calls?tag=name:inventory"
```

If the response indicates the meter does not exist:

1. Confirm `resilience4j-micrometer` is on the runtime classpath.
2. Confirm `MeterRegistry` is created by Spring Boot and not shadowed by a standalone registry.
3. Confirm the `inventory` breaker instance has actually been created and used.
4. Check whether your integration binds metrics automatically or requires binding the registry per that version's approach.
5. Check exact meter names and tags from `/actuator/metrics`.

In an application using a native Resilience4j registry, you can bind metrics manually if auto-binding is absent:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.micrometer.tagged.TaggedCircuitBreakerMetrics;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerMetricsConfiguration {

    public CircuitBreakerMetricsConfiguration(
            CircuitBreakerRegistry circuitBreakerRegistry,
            MeterRegistry meterRegistry) {
        TaggedCircuitBreakerMetrics
            .ofCircuitBreakerRegistry(circuitBreakerRegistry)
            .bindTo(meterRegistry);
    }
}
```

This snippet is for cases where the application manages a native `CircuitBreakerRegistry` without an automatic binder. If the Resilience4j Spring Boot integration or a customizer already binds meters, do not bind them a second time, as that can create duplicate registrations or confusing behavior. Most importantly, the binder and business code must use the same registry/instance.

## 8. Distinguish Missing Meters from No Data Yet

A meter can be registered yet have no meaningful values because no calls have occurred. For instance, the `resilience4j.circuitbreaker.calls` timer only populates after a supplier executes and an outcome is recorded. A state gauge may exist immediately upon breaker creation while timer counts stay at 0.

To verify, trigger a controlled successful call in a dev/test environment and re-query the meter. Then simulate a configured failure and a rejected call while the breaker is `OPEN`. Confirm each outcome appears under the appropriate tags.

Never send live requests to a payment system or production dependency just to generate test metrics. Use mocks, stubs, or a test environment with controlled data and endpoints.

If `/actuator/metrics` lists the meters yet Prometheus has no series, also check:

- Is the Prometheus registry added and auto-configured?
- Does `/actuator/prometheus` return output containing the converted metric names?
- Is Prometheus scraping the right scheme, host, port, path, and authentication?
- Is the target `UP` in Prometheus?
- Are relabeling or metric filtering rules dropping the series?

Micrometer meter names can be transformed for Prometheus export—for example, dots turned into underscores. Search using the exported name from the Prometheus endpoint, not solely the Micrometer name.

## 9. Check Auto-Configuration and the Active Registry

If dependencies and exposure are correct yet indicators or meters are still missing, inspect auto-configuration:

1. Ensure dependencies are on the runtime classpath and match the Spring Boot version.
2. Check startup logs for bean creation errors or unsatisfied auto-configuration conditions.
3. In development, enable the auto-configuration condition evaluation report with `--debug` at startup to see which configurations applied or were skipped.
4. Verify `CircuitBreakerRegistry` and `MeterRegistry` are the beans managed by the expected integration.
5. Verify breaker IDs are created through the same factory/registry observed by the health indicator and metrics binder.

A common mistake is the service calling `CircuitBreakerFactory.create("inventory")` while custom metrics code instantiates its own `CircuitBreakerRegistry.ofDefaults()`. The two registries hold two separate breakers with the same name; metrics from the extra registry will not reflect real calls. Similarly, a health indicator wired to a different registry may always report `CLOSED` even while the factory's breaker is `OPEN`.

Never instantiate a new registry per request or per listener setup. Use a single registry managed in the application context and align instance creation across calling code, metrics, and health.

## 10. Complete Configuration Example

A baseline configuration for a Spring Boot service with Resilience4j, Actuator, and Prometheus may look like:

```yaml
spring:
  application:
    name: order-service

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3

management:
  health:
    circuitbreakers:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
  metrics:
    tags:
      application: ${spring.application.name}
```

Ensure the classpath includes the required dependencies for the backend, Actuator, Micrometer binder, and export registry. Health indicators require a compatible Spring Boot integration or a custom implementation. After startup, verify `/actuator/health`, `/actuator/metrics`, and `/actuator/prometheus` in turn.

## 11. Quick Diagnostic Checklist

| Symptom | Check First | Action |
| --- | --- | --- |
| `/actuator/metrics` returns 404 | Actuator dependency, endpoint enabled, and web exposure | Add Actuator and expose `metrics`; verify port/base path |
| `/actuator/prometheus` returns 404 | Prometheus registry and exposure | Add `micrometer-registry-prometheus`, expose `prometheus` |
| Metrics endpoint exists without Resilience4j meters | `resilience4j-micrometer`, registry, and breaker instance | Add proper binder; verify shared registry and trigger a test call |
| Health endpoint lacks circuit breaker component | Resilience4j Spring Boot integration, global enable, and per-instance registration | Enable health indicator and verify integration/version |
| Health component always `UP` despite breaker `OPEN` | Registry/instance observed by health indicator and version state mapping | Verify same instance; inspect mapping and health config |
| Prometheus lacks series even though Actuator metrics exist | Prometheus registry, scrape target/path, filtering | Check `/actuator/prometheus` and target health |
| Endpoint returns 401/403 | Spring Security or reverse proxy | Grant access to monitoring principal; do not disable security globally |
| Health `DOWN` triggers pod restarts | Liveness/readiness groups | Do not blindly include dependency health in liveness |

## 12. Implementation Rules

- Use the Spring Cloud Resilience4j backend and versions compatible with Spring Boot.
- Add Actuator for operational endpoints; add `resilience4j-micrometer` to bind metrics.
- Add the Prometheus registry when scraping in Prometheus format.
- Use a compatible Spring Boot Resilience4j integration or a custom `HealthIndicator` if a native health contributor is required.
- Enable `registerHealthIndicator` per instance and global health integration according to your version.
- Distinguish enabled endpoints from HTTP-exposed endpoints.
- Verify port, base path, security, and active profile.
- Ensure the health indicator, metrics binder, and calling code observe the same breaker registry/instance.
- Do not use dependency health in liveness probes if it could trigger cascading restarts.
- Verify actual meters via Actuator before writing Prometheus queries or dashboards.

When metrics or health indicators are missing, verify dependencies, auto-configuration, registries, instance IDs, and endpoint exposure in sequence. Checking layer by layer separates Resilience4j integration issues from Actuator or security misconfigurations, while preventing unnecessary changes to circuit breaker runtime behavior when the real problem lies only in observability wiring.

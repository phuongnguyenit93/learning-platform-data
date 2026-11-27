# Health Endpoint in Spring Boot

The health endpoint indicates whether an application is in a suitable state to continue running and receiving traffic. Spring Boot Actuator provides a health endpoint that aggregates status from components such as the database, disk space, messaging, and application-defined health indicators. Load balancers, orchestrators, and monitoring systems can use this result to decide whether to send traffic to an instance. To use it properly, you need to understand what health status reflects, which contributors participate, how to distinguish liveness from readiness, and how to protect internal information.

In the **SPRING_BOOT_OBSERVABILITY** module, the Health endpoint belongs to the **Actuator and Management** chapter, connecting operational mechanisms with metrics, logs, and distributed tracing. This lesson focuses on configuring, extending, and operating the health endpoint in Spring Boot: HealthContributor, HealthIndicator, status aggregation, health groups, Kubernetes probes, security, caching, testing, and troubleshooting.

## Learning Objectives

1. Explain the role of the Actuator health endpoint and health contributors.
2. Read health status and component details.
3. Distinguish between liveness, readiness, and aggregated health.
4. Configure health groups and Kubernetes probes.
5. Write a custom HealthIndicator for a business component.
6. Design dependency checks to avoid cascade restarts.
7. Protect the endpoint and restrict returned information.
8. Control caching, timeouts, and the impact of health checks.
9. Test UP, DOWN, OUT_OF_SERVICE, and UNKNOWN states.

## 1. What Is the Health Endpoint?

Spring Boot Actuator provides the health endpoint to return the overall status of the application and checked components. With default configuration, the endpoint is usually accessed at:

~~~http
GET /actuator/health
~~~

A simple response:

~~~json
{
  "status": "UP"
}
~~~

When showing component details is allowed, the response can include:

~~~json
{
  "status": "UP",
  "components": {
    "db": { "status": "UP" },
    "diskSpace": { "status": "UP" },
    "ping": { "status": "UP" }
  }
}
~~~

Component names and response structure depend on dependencies, contributors, groups, and `show-details` configuration. Do not treat the example as a fixed schema for all applications.

### 1.1. Health Status Is Not Uptime

The health endpoint reflects status at the moment of the check according to participating contributors. It does not prove the application has never failed, does not replace availability history, and does not measure request success rate. To track SLO/uptime, you need metrics, synthetic checks, and historical monitoring.

### 1.2. Health Endpoint Is Not a Business API

The health endpoint serves operational checks. Do not use it to return business data, authenticate users, or provide an admin dashboard. Responses should be small, fast, and stable.

## 2. Actuator Dependencies and Exposure

Add the Actuator starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Keep versions managed by the Spring Boot BOM. Actuator endpoints can be exposed over HTTP or JMX. An endpoint existing in the application context does not mean it is exposed over the web.

Example exposing health and info over HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Expose only endpoints actually needed. Endpoints such as env, configprops, beans, heapdump, or loggers can leak configuration, topology, or internal details. Do not use wildcard exposure in production without evaluating each endpoint and securing access.

### 2.1. Management Port and Base Path

You can configure a dedicated base path or management port:

~~~yaml
management:
  endpoints:
    web:
      base-path: /actuator
  server:
    port: 8081
~~~

When using a separate management port, configure network policies, firewalls, service routing, and probe paths accordingly. A separate management port is not automatically secure just because it differs from the application port.

## 3. Health Contributors and Aggregation

Actuator builds the health response from `HealthContributor` beans. Common types:

- HealthIndicator: a synchronous contributor returning a status.
- ReactiveHealthIndicator: a reactive contributor.
- CompositeHealthContributor: groups multiple contributors.
- HealthContributor: general abstraction for the health tree.

Auto-configured indicators may appear when corresponding dependencies are present, such as database or disk space. The actual list depends on classpath and configuration.

~~~mermaid
flowchart TD
    Endpoint["/actuator/health"] --> Aggregate["HealthEndpoint"]
    Aggregate --> DB["DataSource health"]
    Aggregate --> Disk["Disk space"]
    Aggregate --> Custom["Custom HealthIndicator"]
    Aggregate --> Broker["Messaging health"]
    DB --> Status["Aggregate status"]
    Disk --> Status
    Custom --> Status
    Broker --> Status
    Status --> Response["HTTP response"]
~~~

HealthEndpoint aggregates contributor statuses using a status aggregator. A single DOWN contributor can make the overall health DOWN, depending on the group and aggregation policy.

### 3.1. Common Statuses

| Status | Common Meaning | Possible Action |
| --- | --- | --- |
| UP | Component is operational | Continue serving |
| DOWN | Component is not working | Investigate failure |
| OUT_OF_SERVICE | Should not receive traffic | Remove from load balancing |
| UNKNOWN | Status undetermined | Check indicator/config |

Statuses can be extended. Priority order and HTTP status mapping depend on configuration.

### 3.2. Status Aggregation and HTTP Mapping

The health aggregator picks the overall status based on contributor statuses and priority order. DOWN is usually more severe than UP. If you define custom statuses, configure consistent mapping/ordering so the endpoint and orchestrator interpret them the same way.

Health statuses can map to HTTP status codes such as UP → 200 and DOWN/OUT_OF_SERVICE → 503. UNKNOWN mapping depends on configuration. When changing mappings, verify load balancers and Kubernetes probes handle the response codes properly.

## 4. HealthIndicator and Custom Checks

When Actuator lacks an indicator for an application component, implement `HealthIndicator`:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class SearchIndexHealthIndicator implements HealthIndicator {
    private final SearchIndexClient client;

    public SearchIndexHealthIndicator(SearchIndexClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            if (client.ping()) {
                return Health.up()
                        .withDetail("component", "search-index")
                        .build();
            }
            return Health.down()
                    .withDetail("reason", "search index did not respond")
                    .build();
        } catch (Exception ex) {
            return Health.down(ex).build();
        }
    }
}
~~~

This example illustrates a lightweight check. In production, `client.ping` needs a short timeout, limited retries, and must avoid heavy queries. Consider omitting exception messages or hosts/credentials from public details.

### 4.1. HealthIndicator Must Be Fast and Bounded

The health endpoint can be called frequently by orchestrators. A slow indicator can consume threads, open many connections, or overload the application itself. Each external check should have a small timeout fitting the probe budget, no long retries, lightweight/read-only operations, and concurrency limits if checks can overlap.

### 4.2. Do Not Use Business Transactions as Health Checks

Do not create orders, send payments, or mutate data every few seconds to check health. Use a ping/read-only check or the dependency's official health API. If synthetic business transactions are needed, run them from a dedicated testing system with cleanup.

### 4.3. ReactiveHealthIndicator

For reactive applications, use `ReactiveHealthIndicator` when the check relies on a reactive client. Do not block the event loop waiting for a network check. Apply timeouts using appropriate reactive operators and return a reactive Health result.

## 5. Liveness and Readiness

Liveness and readiness answer two different questions:

- **Liveness:** Is the process/application still alive and capable of continuing on its own?
- **Readiness:** Is the current instance ready to accept traffic?

If liveness fails, the orchestrator may restart the container. If readiness fails, the instance is usually removed from service endpoints/load balancing while continuing to run so it can recover.

### 5.1. Why Not Merge Both Concepts?

If the database temporarily loses connectivity and a database indicator marks liveness DOWN, Kubernetes may restart every pod. Restarting does not fix the database; restarted pods may all reconnect simultaneously and put even heavier load on the database.

Liveness should reflect process/runtime conditions that a restart can fix. Readiness can account for essential dependencies if the application cannot serve requests when that dependency is unavailable.

### 5.2. Enabling Kubernetes Probes

Spring Boot can expose liveness/readiness health groups when probes are enabled:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Common paths:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

In Kubernetes, configure startupProbe, livenessProbe, and readinessProbe to point to the appropriate paths. If the management server runs on a separate port, probes must use that port and network path.

### 5.3. Liveness Group

The liveness group evaluates whether the application is still running and able to continue. Avoid adding databases, brokers, or external APIs to the liveness group if restarting the application cannot fix an outage in that dependency.

### 5.4. Readiness Group

The readiness group evaluates whether the instance can accept traffic. You can include dependencies strictly required on the request path. However, if a shared dependency fails, all pods can become NOT READY simultaneously. Consider degraded mode, fallbacks, circuit breakers, and the ability to handle requests that do not depend on that component.

### 5.5. Startup Probe

Applications may need startup time to warm caches, migrate schemas, or load models. `startupProbe` gives the container a startup window before liveness/readiness checks start taking effect. Configure the startup budget based on real startup duration, rather than raising it indefinitely to mask startup failures.

## 6. Health Groups

Health groups define distinct sets of contributors for each check target. Example:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
        liveness:
          include: livenessState
~~~

Contributor names and group configuration must match your Spring Boot version. Boot can auto-configure probe groups when probes are enabled. If customizing include/exclude, verify the actual contributors and status mapping.

### 6.1. Custom Groups

You can create a custom group for specific dependencies or operations, such as `dependencies`:

~~~yaml
management:
  endpoint:
    health:
      group:
        dependencies:
          include: db,searchIndex
~~~

Verify the group path per endpoint conventions/version. Do not expose sensitive groups publicly if details contain internal information.

### 6.2. Include and Exclude

Group include/exclude decides which contributors participate. An indicator not in the group does not affect that group's status. This keeps liveness isolated from dependency health, but must be documented so the operations team does not confuse overall health with readiness health.

## 7. Dependency Health and Degraded Mode

Not every dependency should make an instance unready. Classify by criticality:

| Dependency | On Failure | Readiness Decision |
| --- | --- | --- |
| Primary database for all requests | Cannot serve main use cases | Can be NOT READY |
| Search index with DB fallback | Search degraded but API still serves | Can stay READY |
| Asynchronous analytics sink | Can buffer/retry | Usually does not affect readiness |
| Optional recommendation API | Has fallback | Usually stays READY |
| Payment provider for payment endpoint | Payment route unusable | Consider dedicated monitoring |

Readiness is the instance's state relative to the traffic it receives, not a report on every dependency in the system. If a service has multiple endpoint types with different dependencies, a single readiness bit can be too coarse; use supplementary monitoring/dependency groups and design clear routing/degraded modes.

### 7.1. Avoid Cascade Failures

If all replicas check a shared dependency and simultaneously become unready when that dependency flickers, traffic can be left with zero healthy instances or trigger a restart/reconnect storm. Combine readiness with circuit breakers, timeouts, bulkheads, and fallbacks. Do not let probes call dependencies with retry storms.

### 7.2. Health Check and Circuit Breaker

The health endpoint does not replace a circuit breaker. A circuit breaker governs business calls based on failure/slow-call behavior. A health indicator reports status to operations systems. Use the same dependency client with sensible timeouts, but do not necessarily tie every internal circuit breaker state directly to readiness.

## 8. Security and Displaying Details

Health details can expose database names, brokers, internal hosts, versions, disk paths, or configuration errors. Configure `show-details` according to requirements and access permissions:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Supported values depend on the Spring Boot version. Use `never` to hide details or `when-authorized` when proper security authorization is in place.

### 8.1. Securing Actuator Endpoints

If management endpoints are exposed over HTTP, configure Spring Security to restrict access. Example separate filter chain for management paths:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ManagementSecurityConfiguration {
    @Bean
    SecurityFilterChain managementSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/actuator/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/actuator/health",
                                "/actuator/health/liveness",
                                "/actuator/health/readiness"
                        ).permitAll()
                        .anyRequest().hasRole("OPS")
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

This is an example separate filter chain; the application may need another chain for business endpoints and appropriate `@Order` precedence. If probes require unauthenticated access, permit only minimal health paths and restrict network access to the management port. Do not open all Actuator endpoints.

### 8.2. Public Status, Private Details

You can allow probes to read status while restricting component details to authorized users. Do not put exception stack traces, credentials, connection URLs, or internal IPs into public responses. Test both anonymous and authorized callers.

## 9. Caching, Timeouts, and Probe Frequency

Health checks may be called every few seconds from multiple orchestrator instances. If every check opens a new connection or calls multiple remote APIs, the endpoint becomes a source of extra load.

### 9.1. Caching Health Results

The Actuator health endpoint supports cache time-to-live in endpoint configuration, depending on version. Example:

~~~yaml
management:
  endpoint:
    health:
      cache:
        time-to-live: 5s
~~~

Caching reduces dependency check frequency at the cost of status staleness. Choose a TTL shorter than your failure detection budget and understand which endpoint/group the cache applies to in your version.

### 9.2. Timeouts Must Be Shorter Than the Probe Budget

If the orchestrator's probe timeout is 2 seconds while an indicator can block for 10 seconds, many probe threads can be tied up. Set each dependency's timeout smaller than the total health request budget. The health endpoint must return quickly or fail fast.

### 9.3. Avoid Health Checks That Load the Database

Do not run full table scans, full-table counts, or heavy business queries. Use lightweight validation such as acquiring a connection and running a constant query if appropriate. Even `SELECT 1` incurs network/connection cost; pick sensible frequency and timeouts.

## 10. Testing the Health Endpoint

Test HTTP responses, status aggregation, group membership, security, and custom indicators.

### 10.1. Testing a Custom HealthIndicator

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;
import static org.assertj.core.api.Assertions.assertThat;

class SearchIndexHealthIndicatorTest {
    @Test
    void reportsDownWhenIndexUnavailable() {
        SearchIndexClient client = () -> false;
        SearchIndexHealthIndicator indicator =
                new SearchIndexHealthIndicator(client);

        assertThat(indicator.health().getStatus()).isEqualTo(Status.DOWN);
    }
}
~~~

This example assumes a client interface with a `ping` method returning boolean. This test verifies the indicator's mapping logic, not HTTP endpoint exposure or security.

### 10.2. Testing the Endpoint with MockMvc

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HealthEndpointTest {
    @Autowired
    MockMvc mvc;

    @Test
    void healthEndpointIsAvailable() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }
}
~~~

Tests require proper exposure and security configuration. If a health check returns DOWN, the endpoint can return 503; status assertions must reflect fixture/indicator state rather than always assuming 200.

### 10.3. Testing Readiness and Liveness Groups

Send requests to both group paths and verify:
- readiness includes the right contributors;
- liveness does not depend on external databases/brokers if required by design;
- a DOWN contributor affects the expected group;
- HTTP status mapping is accurate;
- group details only appear for authorized callers.

### 10.4. Testing Security and Details

Test anonymous callers, callers with the OPS role, and callers lacking the role. Verify public status contains no internal details, authorized details contain only approved information, and other management endpoints remain protected.

## 11. Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| /actuator/health returns 404 | Actuator missing or endpoint not exposed | Check dependency and web exposure |
| Health returns DOWN | A contributor failed | Inspect details with proper authorization and check dependency |
| Health returns 503 though app serves requests | Aggregator/group contributor is DOWN | Check group and HTTP mapping |
| Kubernetes continuously restarts pod | Liveness depends on external dependency | Separate liveness from readiness |
| Pod receives no traffic | Readiness group is DOWN | Verify which dependencies are truly mandatory |
| Probe timeout | Indicator blocks or retries too long | Short timeouts, caching, and lower check cost |
| Component details do not appear | show-details policy or authorization | Check security and config |
| Custom indicator missing | Bean not scanned or excluded from group | Check component scan/group |
| Health checks increase DB load | Heavy query or overly frequent probes | Lightweight check and TTL |
| Status UNKNOWN | Contributor failed to determine status | Handle fallback/status mapping |
| All pods unready when broker fails | Shared dependency check causes cascade | Degraded mode and readiness policy |
| Health endpoint leaks topology | Details exposed to anonymous callers | Hide details and restrict access |

### 11.1. Investigation Procedure

1. Call the aggregate health endpoint and determine the status.
2. If authorized, inspect component details to find the failing contributor.
3. Check which group the probe is calling: liveness or readiness.
4. Verify indicator timeouts and dependency availability.
5. Check HTTP status mapping, security, and management port.
6. Correlate with dependency logs/metrics.
7. Check cache TTL and probe frequency.
8. If Kubernetes is restarting pods, verify whether liveness depends on external systems.

## 12. Production Checklist

| Criterion | Required Evidence |
| --- | --- |
| Actuator health exposed | Only necessary paths |
| Liveness and readiness separated | Group membership tested |
| Clear dependency policy | Mandatory vs. optional dependencies classified |
| Lightweight custom indicators | Timeouts, read-only, no long retries |
| Clear status aggregation | DOWN/OUT_OF_SERVICE/UNKNOWN mapping |
| Proper security | Public status, private details |
| Restricted management network | Port/firewall/network policy |
| Sensible cache TTL | Not stale beyond failure budget |
| Appropriate probe budgets | Startup/liveness/readiness timeouts |
| No cascade restarts | Liveness independent of external services |
| Details redacted | No credentials/internal data |
| Comprehensive tests | UP/DOWN, groups, security, timeouts |
| Historical monitoring | Metrics/alerts complementing point-in-time health |

## 13. Hands-On: Configuring Health Probes for order-service

**Context:** order-service runs on Kubernetes and depends on PostgreSQL and inventory-service. During a brief PostgreSQL outage, pods are restarted continuously even though the JVM is healthy and could recover once the database returns.

**Tasks:**
1. Add Spring Boot Actuator and expose the health endpoint.
2. Enable liveness/readiness probes for your Spring Boot version.
3. Ensure the liveness group reflects only process/runtime state.
4. Include the database indicator in readiness if the database is a mandatory dependency for traffic.
5. Create a custom SearchIndexHealthIndicator or equivalent indicator with a short timeout.
6. Verify behavior when the database is DOWN while the process remains running.
7. Configure Kubernetes startupProbe/livenessProbe/readinessProbe with the right paths and port.
8. Protect component details; expose only minimal status publicly for probes.
9. Experiment with cache TTL and measure impact on probe freshness.
10. Test security, group membership, status aggregation, and timeouts.
11. Verify a database outage does not trigger a liveness restart storm.
12. Write a runbook distinguishing unhealthy pod, unready pod, and degraded dependency.

**Expected deliverables:** Actuator configuration, custom health indicator, probe groups, Kubernetes probe setup, integration tests, and operational runbook.

## 14. Takeaway

The health endpoint provides point-in-time status from HealthContributors. It supports load balancers, orchestrators, and monitoring, but does not replace historical metrics or synthetic checks. Liveness answers whether the process should continue running; readiness answers whether the instance should receive traffic. Both groups need distinct contributor memberships by design.

Custom indicators must be fast, read-only, time-bounded, and avoid significant load. Do not put external dependencies into liveness if restarting the application cannot fix their outages. Protect component details, limit Actuator exposure, configure the management network, and test status/security mappings. Use the health endpoint for immediate operational decisions; use metrics, logs, and traces to find root causes.

**References:**
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Health Information](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot — Actuator Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.security)
- [Spring Boot — Monitoring and Management](https://docs.spring.io/spring-boot/reference/actuator/)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)

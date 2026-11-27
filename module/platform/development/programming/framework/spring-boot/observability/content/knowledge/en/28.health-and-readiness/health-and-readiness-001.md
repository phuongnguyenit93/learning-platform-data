# Health Indicators in Spring Boot Actuator

> **Chapter:** Health and readiness  
> **Lesson:** Health indicator  
> **Module:** SPRING_BOOT_OBSERVABILITY — Set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. What is a health indicator?

A health indicator is a component that reports the state of a resource or capability that the application depends on. Spring Boot Actuator aggregates the results into a health endpoint so operations systems know whether the application is functioning normally, ready to receive traffic, or whether any dependency is experiencing issues.

A service may require a database, message broker, filesystem, external API, or internal worker. A health indicator should answer a specific operational question, such as whether the database can execute a lightweight check. It should not run an entire business workflow or generate heavy load each time the health endpoint is called.

~~~mermaid
flowchart TD
  A["GET /actuator/health"] --> B["HealthEndpoint"]
  B --> C["HealthContributorRegistry"]
  C --> D["DatabaseHealthIndicator"]
  C --> E["BrokerHealthIndicator"]
  C --> F["DiskSpaceHealthIndicator"]
  D --> G["Health status + details"]
  E --> G
  F --> G
  G --> H["Aggregate health response"]
~~~

A health indicator is one part of health reporting. It does not replace metrics, tracing, alerting, or synthetic tests. Health indicates the state at the moment of the check; metrics and traces help understand trends, root causes, and impact.

## 2. HealthIndicator and HealthContributor

Spring Boot Actuator provides abstractions for health contributors. A synchronous `HealthIndicator` performs a check and returns `Health`. `ReactiveHealthIndicator` provides asynchronous health results for reactive applications.

~~~java
public interface HealthIndicator {
    Health health();
}
~~~

A custom indicator typically implements `HealthIndicator` and is registered as a Spring bean. Actuator discovers contributors in the application context and adds them to the registry.

`HealthContributor` is a broader abstraction, which can be a single indicator or a group of contributors. `CompositeHealthContributor` groups multiple contributors into a hierarchical structure.

| Component | Role |
| --- | --- |
| HealthIndicator | Synchronous check, returns Health |
| ReactiveHealthIndicator | Reactive check, returns Publisher/Mono Health |
| HealthContributor | General abstraction for a health contribution |
| CompositeHealthContributor | Groups multiple child contributors |
| Health | Status and details of a single check |
| Status | Standardized result such as UP, DOWN, OUT_OF_SERVICE, UNKNOWN |

Choose contributors based on dependencies/capabilities that are meaningful for operations; do not create a separate indicator for every class or method.

## 3. Health response structure

A health result has a status and may include details. Example response:

~~~json
{
  "status": "UP",
  "components": {
    "db": { "status": "UP" },
    "diskSpace": { "status": "UP" }
  }
}
~~~

The actual response depends on endpoint access, the show-details policy, health groups, and the Spring Boot version. When details are not permitted to be shown, callers may only receive the aggregated status.

Common statuses:
- UP: the contributor is functioning normally.
- DOWN: the contributor is not functioning according to the check.
- OUT_OF_SERVICE: the contributor is temporarily out of service.
- UNKNOWN: the state cannot be determined.

Status is operational data, not an exception message. Details must not expose credentials, SQL, connection strings, or personal data.

## 4. Writing a custom HealthIndicator

Example indicator checking file storage capability:

~~~java
@Component
public class ArchiveStorageHealthIndicator implements HealthIndicator {

    private final ArchiveStorageClient storageClient;

    public ArchiveStorageHealthIndicator(ArchiveStorageClient storageClient) {
        this.storageClient = storageClient;
    }

    @Override
    public Health health() {
        try {
            boolean available = storageClient.isAvailable();
            if (available) {
                return Health.up()
                        .withDetail("storage", "reachable")
                        .build();
            }
            return Health.down()
                    .withDetail("storage", "unavailable")
                    .build();
        } catch (Exception ex) {
            return Health.down(ex)
                    .withDetail("storage", "health check failed")
                    .build();
        }
    }
}
~~~

The example assumes `ArchiveStorageClient` has an `isAvailable()` method that is fast, safe, and free of side effects. If the method makes a network call, it needs a short timeout, must avoid long retries, and must ensure the health check does not exhaust the connection pool.

Do not return UP merely because the client object has been created. The indicator must verify the actual capability the application needs within appropriate time/cost limits.

### 4.1. Returning status and details intentionally

Details should use stable fields such as dependency name, check type, or simple status. Do not include secrets, tokens, passwords, raw exception messages, query parameters, or payloads. Do not put stack traces into health details; stack traces belong in logs/tracing with separate access and retention controls.

## 5. ReactiveHealthIndicator

In a reactive application, a health check may call a dependency via a reactive client. Implement `ReactiveHealthIndicator` so it does not block the event-loop thread.

~~~java
@Component
public class SearchServiceHealthIndicator
        implements ReactiveHealthIndicator {

    private final WebClient webClient;

    public SearchServiceHealthIndicator(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://search-service")
                .build();
    }

    @Override
    public Mono<Health> health() {
        return webClient.get()
                .uri("/internal/health")
                .retrieve()
                .toBodilessEntity()
                .timeout(Duration.ofSeconds(2))
                .map(response -> Health.up()
                        .withDetail("search-service",
                                response.getStatusCode().value())
                        .build())
                .onErrorResume(ex -> Mono.just(
                        Health.down()
                                .withDetail("search-service", "unavailable")
                                .build()));
    }
}
~~~

This is an illustrative example; appropriate Reactor, `WebClient`, and `Health` API imports are required. The downstream endpoint must be a lightweight, protected health contract with a timeout. Do not call expensive business endpoints to check health.

If a reactive indicator calls `block()`, it can occupy the event-loop thread and slow down the application itself. Use reactive APIs end-to-end and enforce timeouts.

## 6. Status aggregation

The health endpoint aggregates statuses from multiple contributors. If one contributor is DOWN, the overall status changes according to the status aggregator and configured order.

For example: if DB is UP, broker is UP, and disk is UP, the total is UP; if DB is DOWN, the total may become DOWN; OUT_OF_SERVICE has precedence according to policy.

Status order can be configured:

~~~yaml
management:
  endpoint:
    health:
      status:
        order: DOWN, OUT_OF_SERVICE, UP, UNKNOWN
~~~

Exact property names must match the Spring Boot version. When customizing statuses, check both aggregation and HTTP status mapping; avoid creating custom statuses that the platform/probes do not understand.

UNKNOWN should not automatically be interpreted as UP. If a check cannot be performed, choose clear semantics according to policy and display a safe reason.

## 7. HTTP status mapping for health

The health endpoint typically maps the aggregated state to an HTTP response status. UP usually returns 200; DOWN or OUT_OF_SERVICE usually maps to a service error status according to the default mapping. UNKNOWN and custom statuses require checking the specific configuration.

Kubernetes HTTP probes usually only need to distinguish between a successful or failed response. Monitoring systems can read the JSON status and component details if authorized.

Do not assume all health statuses map identically across versions or custom mappings. Verify the actual response of the endpoint in the running profile.

## 8. Health groups: liveness and readiness

Health groups allow selecting a dedicated set of contributors for a specific check purpose:
- Liveness: does the process need to be restarted?
- Readiness: is the instance ready to receive traffic?

Example configuration:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
        liveness:
          include: livenessState
~~~

The example illustrates including contributors. Carefully consider whether to include the database in readiness: if the API cannot serve requests when the DB is down, readiness can reflect that dependency; if only part of the API needs the DB or there is a widespread dependency outage, putting the DB into the readiness of every pod may remove all replicas from traffic.

Do not put typical database/broker/network dependencies into liveness. A temporary dependency error does not mean the process needs to restart. Mass restarts can worsen an incident.

## 9. Which dependencies should have a health indicator?

| Dependency/capability | Should it have an indicator? | Considerations |
| --- | --- | --- |
| Primary database | Usually yes | Lightweight check, short timeout; distinguish readiness/liveness |
| Message broker | Depends on role | If unable to accept work when the broker is down, readiness may need to reflect it |
| Optional recommendation API | Usually excluded from overall readiness | The main API can still function |
| Disk storing mandatory data | May be needed | Disk space indicator and reasonable threshold |
| External payment provider | Depends on contract | Do not create transactions to check |
| Cache | Depends on whether cache is mandatory | Cache down may only increase latency |
| Scheduler | May have a capability indicator | Check worker progress, not just that the thread is alive |

The health policy should align with request-serving capability and SLAs. An optional dependency being DOWN may only warrant a warning/metric instead of marking the entire service DOWN.

## 10. Avoid health checks that create load or side effects

Health checks are called periodically by kubelet, load balancers, monitoring agents, and operators. If every check runs heavy queries or calls numerous dependencies, the health endpoint can become a new source of load.

Good design:
- Short and bounded timeouts.
- No long retries.
- Use lightweight queries or native pings if appropriate.
- Cache results for a short duration if semantics permit.
- Limit concurrency.
- Do not create transactions or write business data.
- Do not call transaction-creating APIs.
- Do not expose exception messages.

The health endpoint must remain stable when a dependency fails. If an indicator waits indefinitely, probe timeouts can generate extra load and trigger restarts.

## 11. Health indicators and metrics/tracing

A health indicator is a status snapshot. Metrics and tracing provide data over time and per operation.

For example:
- Health: database DOWN at check time.
- Metrics: connection pool pending count increasing over 10 minutes.
- Traces: slow query spans due to lock wait.
- Logs: database connection acquisition timeout.

Do not replace health checks with a single metric threshold. Nor should you create a health indicator for every metric. Health statuses need clear semantics and serve readiness/liveness decisions.

If a health indicator calls a dependency via `WebClient`/JDBC, that call may generate its own telemetry. Consider avoiding excessive trace/log generation from health polling while retaining necessary diagnostic data.

## 12. Composite health contributors

When a subsystem consists of multiple components, `CompositeHealthContributor` represents a health tree.

~~~text
storage
  primary
  replica
~~~

The response can show the status of each child contributor if the caller is authorized to view details. Composites help identify which component failed without creating one giant indicator.

Contributor names should be stable and easy to understand. Avoid using dynamic instance IDs or tenant IDs as contributor names if they create an unbounded number of entries.

## 13. Custom health statuses

An application can define a custom `Status`, such as `DEGRADED`, when a dependency is still operating but a capability is impaired. If using a custom status:
- Define its precedence order in `StatusAggregator`.
- Configure HTTP mapping if needed.
- Determine whether readiness considers `DEGRADED` as ready.
- Ensure probes/monitoring understand the status.
- Document semantics and alerting policies.

Do not create dozens of custom statuses for minor errors. Status should be a small, stable taxonomy; details belong in health details, metrics, and logs.

## 14. Securing the health endpoint

A health response can reveal database names, brokers, internal services, hostnames, disk paths, or dependency topology. Only expose details to authorized callers.

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Supported values depend on the version. Configure appropriate security roles for operators to read details, while public callers only see the overall status if policy requires.

Do not put credentials, connection URLs containing passwords, SQL statements, stack traces, or raw exception messages into details. The health endpoint is not a debug dump.

## 15. Testing a custom health indicator

Test the indicator directly with a mocked dependency:

~~~java
class ArchiveStorageHealthIndicatorTest {

    @Test
    void reportsDownWhenStorageIsUnavailable() {
        ArchiveStorageClient client = mock(ArchiveStorageClient.class);
        when(client.isAvailable()).thenReturn(false);

        ArchiveStorageHealthIndicator indicator =
                new ArchiveStorageHealthIndicator(client);

        Health health = indicator.health();

        assertThat(health.getStatus()).isEqualTo(Status.DOWN);
    }
}
~~~

In addition to unit tests, integration-test the endpoint:
- The contributor is registered in the Spring context.
- The endpoint returns the correct overall status.
- Readiness/liveness groups include the right contributors.
- HTTP mapping matches platform probes.
- Details are hidden from unauthorized callers.
- Dependency timeouts do not hang the endpoint.
- Reactive indicators do not block the event loop.

Do not test only the happy path. Simulate timeouts, exceptions, unknown results, and multiple contributors with differing statuses.

## 16. Troubleshooting health indicators

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Health is DOWN even though API still serves requests | Indicator checks an optional dependency | Adjust readiness membership/semantics |
| Health is UP but business requests fail | Check is too shallow | Review the endpoint/check contract |
| Probe timeout | Indicator blocks or dependency lacks timeout | Bounded timeout, reactive/non-blocking |
| Continuous liveness restarts | External dependency included in liveness | Use only process-local liveness signals |
| Readiness DOWN across all replicas | Shared dependency failed and policy removes all | Review failure domain/fallback |
| Component does not appear | Bean not registered or registry issue | Check Spring context |
| Details not shown | show-details/security policy | Check role and endpoint access |
| Custom status returns unexpected HTTP code | StatusAggregator/HttpCodeStatusMapper | Check order and mapping |
| Reactive indicator causes thread starvation | Blocking on the event loop | Use reactive client and timeout |
| Health endpoint creates heavy load | Polling too frequently/heavy check | Make lighter, add bounded caching |
| Health response exposes topology | show-details too permissive | Restrict access and sanitize |

### Investigation workflow

1. Identify which endpoint/group the probe is calling.
2. Check the contributors belonging to that group.
3. Read status/details according to granted permissions.
4. Identify which check is slow or failing.
5. Correlate with metrics, traces, and dependency health.
6. Check timeouts, retries, and blocking behavior.
7. Review HTTP status mapping and probe thresholds.
8. Adjust liveness/readiness semantics instead of merely extending timeouts.

## 17. Real-world scenario: database fails while the process stays alive

**Context:** `order-service` runs multiple replicas. The database experiences a brief outage. Aggregate health turns DOWN and the Kubernetes liveness probe starts restarting pods.

### Step 1 — identify the indicator causing DOWN

The health response shows the `db` contributor is DOWN. The process and management endpoint still respond, but the database connection check fails.

### Step 2 — check which group the probe uses

If the liveness group includes `db`, every pod can fail liveness and restart. Restarting does not recover the database and causes a loss of worker capacity.

### Step 3 — separate liveness and readiness

Liveness should only reflect appropriate process-local conditions. Readiness can include `db` if the service cannot handle business requests when the DB is unavailable.

### Step 4 — consider the failure domain

If the database fails across the region, all replicas may become not-ready together. This can be the right state if there is no fallback. If the service has read-only endpoints or cache fallbacks, the readiness policy needs to reflect actual capabilities.

### Step 5 — verify

Simulate a DB outage in a test environment. Confirm:
- Liveness remains UP when the process is healthy.
- Readiness is DOWN if requests cannot be served.
- Pods do not enter a restart loop.
- The health endpoint has a finite timeout.
- When the DB recovers, readiness automatically returns to UP.
- Metrics/traces/logs provide the detailed root cause.

**Expected outcome:** the platform only restarts a process when the process needs restarting; traffic is routed based on readiness semantics.

## 18. Practice exercises and self-check questions

### Exercise A — custom synchronous indicator

Write a `HealthIndicator` that checks a storage client. Test UP, DOWN, and exceptions. Ensure details contain no secrets or raw exception messages.

### Exercise B — reactive indicator

Write a `ReactiveHealthIndicator` calling a mocked `WebClient` endpoint. Test success, HTTP error, timeout, and cancellation. Verify `block()` is not used on the event loop.

### Exercise C — health groups

Configure liveness/readiness groups. Put the DB only in readiness, not in liveness. Simulate a DB outage and inspect probe responses.

### Exercise D — aggregation and mapping

Create two contributors with UP/DOWN/OUT_OF_SERVICE. Observe the aggregate status and HTTP response. Test status order and custom mapping in a test profile.

### Exercise E — security

Configure `show-details: when-authorized`. Test with an unauthenticated caller, an OPS role, and a probe account. Verify there are no credentials/connection strings in the response.

### Exercise F — dependency outage

Simulate a broker/database unavailable state. Measure health endpoint duration, pool usage, and probe failures. Ensure the health check does not create significant load or a retry storm.

### Self-check questions

1. How do `HealthIndicator` and `ReactiveHealthIndicator` differ?
2. When are `HealthContributor` and `CompositeHealthContributor` used?
3. What do UP/DOWN/OUT_OF_SERVICE/UNKNOWN indicate?
4. How does health aggregation work when there are multiple contributors?
5. Why do health details need access control?
6. What operational decision distinguishes liveness from readiness?
7. Why should databases/brokers not be placed in liveness by default?
8. How can a health check overload the system?
9. Why must a reactive health check not block the event loop?
10. How does a health snapshot differ from metrics/tracing?
11. When should an optional dependency not mark the service DOWN?
12. How do custom statuses need aggregation and HTTP mapping configured?
13. How do you test indicator timeouts and exceptions?
14. Why does health UP not guarantee all business requests will succeed?
15. How do you investigate readiness DOWN without creating a restart loop?

**Completion criteria:** create custom sync/reactive health indicators; understand contributors/composites and aggregation; configure health groups; distinguish liveness/readiness; limit timeouts/side effects; secure details; test status mapping and outage behavior; correlate health with metrics/traces/logs.

## 19. Key takeaways

- A health indicator reports the status of a dependency or capability at check time.
- `HealthIndicator` is synchronous; `ReactiveHealthIndicator` is suited for reactive checks and should not block the event loop.
- `HealthContributor`/`CompositeHealthContributor` organize indicators by subsystem.
- UP/DOWN/OUT_OF_SERVICE/UNKNOWN are common statuses; the aggregate result depends on `StatusAggregator` and configuration.
- Liveness decides whether the process needs to restart; readiness decides whether the instance receives traffic.
- Temporary dependency failures should generally affect readiness per contract, not automatically fail liveness.
- Health checks must be lightweight, bounded, have finite timeouts, and produce no business side effects.
- Details can expose topology/secrets; apply appropriate `show-details` and authorization.
- A health snapshot complements metrics, traces, and logs; it does not replace them.
- Test success, failure, timeout, status mapping, security, and dependency outages before using probes in production.

## References

- [Spring Boot Reference — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Spring Boot Reference — Health Groups](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health.groups)
- [Spring Boot Reference — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot API — HealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/health/HealthIndicator.html)
- [Spring Boot API — ReactiveHealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/health/ReactiveHealthIndicator.html)
- [Spring Boot API — CompositeHealthContributor](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)

# Health Unexpectedly Reporting DOWN in Spring Boot

## 1. Objectives and Context

The application still accepts requests, yet `/actuator/health` returns `DOWN` or HTTP 503. Kubernetes may mark the Pod as unready, the load balancer may stop routing traffic, or the liveness probe may restart the container. This symptom usually appears when an external dependency health contributor fails, status aggregation alters the overall result, or a custom indicator misinterprets state.

The health endpoint accurately reflects the contributors included in the queried group and their status aggregation rules. `DOWN` does not necessarily mean the JVM has died or that every business function has stopped working. You need to identify which component is reporting a failure, which group is being probed, and what the consumer does with that result.

This lesson belongs to the **Troubleshooting** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

After this lesson, you will be able to:
1. Read the aggregate status and component details of Actuator health.
2. Find the contributor causing a health group to transition to `DOWN`.
3. Distinguish overall health, liveness, and readiness.
4. Check status aggregation, ordering, and HTTP mapping.
5. Diagnose custom `HealthIndicator` implementations, timeouts, and dependency failures.
6. Avoid external dependency probes triggering restart loops.
7. Write tests reproducing the `DOWN` state and verify recovery.

**Baseline:** Spring Boot 3.5.x, Java 17+, Spring Boot Actuator. Specific health contributors and properties depend on dependencies, application configuration, and version.

## 2. Identify Which Endpoint and Consumer Are Reporting Failure

First identify which URL is being called and who is calling it:

| Endpoint | Common Consumer | Meaning |
| --- | --- | --- |
| `/actuator/health` | Operator, dashboard, load balancer | Aggregate health of the default group |
| `/actuator/health/readiness` | Kubernetes readiness probe | Whether the instance should receive traffic |
| `/actuator/health/liveness` | Kubernetes liveness probe | Whether the process needs to be restarted |
| `/actuator/health/{group}` | Monitoring or operator | Aggregate of a custom group |

Do not infer from an HTTP 503 that the entire application is down. Record the exact endpoint, timestamp, Pod/instance, profile, and probe type. A readiness group may be `DOWN` while liveness stays `UP`; that can be expected behavior when a dependency is not yet ready.

## 3. Reading Aggregate Status and Component Details

When permitted to view details, call the endpoint:

```bash
curl -i http://localhost:8080/actuator/health
```

Example response:

```json
{
  "status": "DOWN",
  "components": {
    "db": {
      "status": "DOWN",
      "details": {
        "error": "Connection refused"
      }
    },
    "diskSpace": {
      "status": "UP"
    },
    "ping": {
      "status": "UP"
    }
  }
}
```

Illustrative example. Component names and detail fields depend on the contributor. Here `db` is the first clue: disk and process ping are still `UP`, while the database health check cannot connect.

If the response contains only `{"status":"DOWN"}`, details may be hidden by policy. Do not enable public display of details for debugging. Use an authorized operator principal or check internal logs/metrics.

## 4. Understanding Status Aggregation

Actuator collects statuses from contributors in the group and uses `StatusAggregator` to produce the overall result. By default, more severe statuses dominate the aggregate. Consequently, a single `DOWN` contributor can bring down the whole group even when all other components are `UP`.

Common statuses:

| Status | General Meaning |
| --- | --- |
| `UP` | Contributor is functioning normally |
| `DOWN` | Contributor is failing per health check |
| `OUT_OF_SERVICE` | Component should not serve traffic |
| `UNKNOWN` | State cannot be determined |

An application can define custom statuses. If a custom status is not listed in `status.order`, precedence may behave unexpectedly. Check actual statuses and aggregator configuration instead of assuming `DOWN` is the only status that can fail the aggregate.

Example order configuration:

```yaml
management:
  endpoint:
    health:
      status:
        order: DOWN, OUT_OF_SERVICE, UNKNOWN, UP
```

Only change the ordering once status semantics are agreed upon. Placing a custom status at lower priority than `UP` can make health report `UP` while a contributor indicates traffic should stop.

## 5. Identifying the Contributor Causing DOWN

Proceed in order:

1. Fetch component details via an authorized endpoint/group.
2. Record contributor name, status, exception class, and timestamp.
3. Correlate with logs from the exact same instance and timestamp.
4. Check the corresponding dependency using independent health/metrics.
5. Confirm whether the contributor belongs to the group being probed.
6. Check whether the contributor is auto-configured from a dependency or registered by the application.

Common contributors:

| Contributor | Common Causes of DOWN | What to Check |
| --- | --- | --- |
| `db` | DB unavailable, wrong credentials, exhausted pool, network error | DB connectivity, pool active/pending/timeouts, secrets/config |
| `diskSpace` | Free space below threshold | Filesystem, volume mount, threshold |
| `redis`/cache | Cache server unreachable | DNS, auth, timeout, server health |
| `mongo`/search | Dependency unavailable | Connection string, TLS, server status |
| `rabbit`/messaging | Broker unreachable or wrong credentials | Broker health, network, credentials |
| Custom indicator | Bug/exception/timeout in code | Source, timeout, logs, and unit tests |

Not every application has all these contributors. They normally appear when the matching dependency and auto-configuration are present.

## 6. Database Health Reporting DOWN

The database indicator may execute a validation check against the datasource. `DOWN` can be caused by:
- Database server stopped or undergoing failover.
- DNS, routing, firewall, or TLS handshake failure.
- Wrong or recently rotated username/password/secret.
- Connection pool exhausted or unable to open new connections.
- Database connection limit reached.
- Health query blocked by locks or database overload.
- Health check timeout too short for the environment.

Check simultaneously:

```text
Application:
  hikaricp active / idle / max / pending / timeout
  JDBC connection errors
  datasource health duration

Database:
  server availability
  active sessions / max connections
  lock waits / deadlocks
  CPU / disk / replication state
```

If business queries succeed while the health query fails, review the health indicator, validation query, datasource routing, and credentials used by the indicator. Do not disable the health check just to turn status green while a dependency is genuinely unstable.

## 7. DiskSpace Health Reporting DOWN

The disk space contributor typically compares free filesystem space against a threshold. It can report `DOWN` when:
- Container writable layer is nearly full.
- Log files grow unbounded.
- Temporary files or heap dumps consume space.
- Persistent volume is nearly exhausted.
- The indicator checks a different filesystem from the volume storing critical data.

Inspect the filesystem from inside the actual container/Pod and compare with the path checked by the indicator. Do not arbitrarily raise the threshold to hide disk exhaustion risk. Address the root cause: log rotation, retention, temporary-file cleanup, or volume expansion per capacity policy.

## 8. Health Groups and Readiness/Liveness

Overall health may contain more contributors than readiness/liveness. Check group configuration:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
        liveness:
          include: livenessState
```

This example includes the database in readiness and uses only liveness state for liveness. Deciding to include DB in readiness must be based on whether the service can handle meaningful traffic if the DB is unavailable.

**Liveness** should reflect whether the process can keep running and self-recover. Do not include databases, remote APIs, or brokers in liveness by default. If a shared dependency goes down, every Pod could restart simultaneously and trigger a restart storm.

**Readiness** decides whether the instance receives traffic. If a mandatory dependency is unavailable, readiness may go `DOWN` to stop routing traffic to the instance. However, if an optional dependency fails, the entire service does not necessarily need to be marked `NOT_READY`.

Verify Kubernetes probe settings: path, port, initial delay, period, timeout, and failure threshold. Overly aggressive probes can turn a brief spike into instability.

## 9. Custom HealthIndicator Always Returning DOWN

Custom indicators frequently fail due to:
- Incorrect dependency injection or uninitialized client.
- Calling a remote service without a timeout.
- Catching exceptions and always returning `Health.down()`.
- Wrong condition logic, such as treating null/empty as unavailable.
- Causing side effects or running heavy business queries.
- Running the indicator on an unsuitable thread/event loop.

Example implementation with timeout and state differentiation:

```java
@Component
class SearchHealthIndicator implements HealthIndicator {
    private final SearchClient client;

    SearchHealthIndicator(SearchClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            client.pingWithTimeout(Duration.ofSeconds(2));
            return Health.up().build();
        } catch (SearchUnavailableException ex) {
            return Health.down()
                    .withDetail("reason", "search unavailable")
                    .build();
        }
    }
}
```

This example uses a hypothetical application API `pingWithTimeout`; replace it with a real client configured with a bounded timeout. Return only safe details; never expose exception messages containing hosts, credentials, or request data in the response.

Do not catch every `Exception` and return `DOWN` without internal logging/metrics. Preserve the exception class and root cause on a protected channel to distinguish configuration errors, network errors, and programming bugs.

## 10. Timeouts and Hanging Health Checks

The health endpoint can become slow if contributors call dependencies sequentially or wait indefinitely. When multiple probes arrive concurrently, health checks can add load onto an already overloaded dependency.

Check:
- Timeouts on HTTP/JDBC clients used by indicators.
- Number of contributors running sequentially/concurrently and total response time.
- Whether thread pools/executors or event loops are blocked.
- Whether the health check opens a fresh connection/query on every call.
- Whether brief health result caching is appropriate.

Only cache if semantics and freshness allow; do not cache `DOWN`/`UP` too long or probes will fail to reflect recovery. On reactive stacks, use `ReactiveHealthIndicator` and non-blocking clients; never block the event loop.

## 11. Security Hiding Details or Blocking Probes

Health details can be hidden by:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
```

`when-authorized` reveals details only to callers authenticated/authorized per Spring Security configuration. If Kubernetes kubelet or a load balancer receives 401/403, the probe can fail even while component statuses are `UP`.

Check the active `SecurityFilterChain`, request matchers, management port, and probe identity. Permit probe paths per network/identity policy; do not open all of Actuator or switch to `show-details: always` just to resolve a 401.

## 12. Status Mapping and HTTP 503

Aggregate status maps to an HTTP status code. Under common defaults, `UP` returns 200 and `DOWN`/`OUT_OF_SERVICE` return 503. Status ordering and HTTP mapping can be customized.

Example:

```yaml
management:
  endpoint:
    health:
      status:
        http-mapping:
          DOWN: 503
          OUT_OF_SERVICE: 503
          UP: 200
```

If the UI shows `DOWN` yet HTTP returns 200, check custom mappings. If contributors are `UP` yet the endpoint returns 503, inspect aggregate contributors/groups and custom status mappings. Do not change HTTP mappings to mask failures: orchestrators could keep routing traffic to an unready instance.

## 13. Quick Investigation Workflow

1. Identify the exact endpoint: overall, readiness, liveness, or custom group.
2. Record instance/Pod, timestamp, profile, and HTTP status.
3. Retrieve component details using authorized operator access.
4. Identify the first contributor whose status is not `UP`.
5. Inspect logs, exception class, and dependency metrics for that contributor.
6. Verify health group include/exclude settings and auto-configured contributors.
7. Check timeouts, status order, custom statuses, and HTTP mapping.
8. Cross-check Kubernetes probe path/port/thresholds.
9. Fix the root cause and confirm the contributor returns to `UP`.
10. Verify readiness/liveness and traffic routing recover properly; monitor to ensure no recurrence.

## 14. Tests to Reproduce Unexpected DOWN

### 14.1. Unit Testing a Custom Indicator

Mock the dependency to test each branch:
- Healthy dependency → `UP`.
- Unavailable dependency → `DOWN` or `OUT_OF_SERVICE` per policy.
- Timeout → defined status without hanging the test.
- Unexpected exception → recorded internally without leaking sensitive data.

### 14.2. Integration Testing the Health Endpoint

```java
mockMvc.perform(get("/actuator/health"))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.status").value("DOWN"));
```

This test assumes the test health contributor is `DOWN` and default/configured HTTP mapping returns 503. Set up explicit fixtures; do not depend on a real database or network in unit tests.

### 14.3. Testing Groups and Probes

- Database `DOWN` does not make liveness `DOWN` if DB is outside the liveness group.
- Database `DOWN` makes readiness `DOWN` only when it is a mandatory, included dependency.
- Contributors outside a group do not affect that group's result.
- Unauthorized callers cannot see details.
- Probe path/port in Kubernetes match management/server configuration.

## 15. Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Overall health `DOWN` while readiness is `UP` | Secondary contributor in overall group is `DOWN` | Check component details and group membership |
| Readiness `DOWN`, liveness `UP` | Mandatory dependency not yet ready | Check dependency; avoid restarting process while alive |
| All Pods restart when DB is down | DB is included in the liveness group | Move dependency check to readiness if appropriate |
| DB component `DOWN` while business queries run | Health query/credentials/route differ from business datasource | Inspect the indicator and actual datasource |
| `DiskSpace` `DOWN` | Filesystem path below threshold | Check the exact mount, logs, temp files, and volume |
| Custom indicator always `DOWN` | Wrong logic/exception/timeout | Unit test branches and set bounded timeout |
| Health endpoint hangs | Contributor I/O has no timeout or blocks threads | Bounded timeouts, non-blocking client, reduce probe cost |
| HTTP 503 while components are `UP` | Custom status/aggregator or group mismatch | Inspect status order and actually queried contributors |
| HTTP 200 despite degraded custom status | Unsuitable HTTP mapping or status order | Verify consumer semantics and mappings |
| Kubernetes probe 401/403 | Security matcher blocks kubelet | Adjust probe path access per policy |
| Details do not appear | Hidden by `show-details`/`show-components` | Use an authorized operator identity |
| Status flaps `UP`/`DOWN` | Flaky dependency or overly frequent probes | Review latency/error timeline, timeouts, and thresholds |
| Probe fails after deployment | Startup incomplete or initial delay too short | Check startup/readiness state and probe timing |

## 16. Production Checklist

- [ ] Know which endpoints/groups are called by load balancers and orchestrators.
- [ ] Can identify the contributor causing `DOWN` via details or internal logs.
- [ ] `StatusAggregator` order and HTTP mappings are clearly understood.
- [ ] Liveness checks only the process's ability to self-recover.
- [ ] Readiness includes only dependencies necessary to serve traffic.
- [ ] Custom indicators are fast, have timeouts, and have no side effects.
- [ ] Database/disk/network checks are verified from the exact runtime environment.
- [ ] Health details are protected by authorization.
- [ ] Probe path, port, timeout, period, and thresholds have been tested.
- [ ] Tests cover `UP`, `DOWN`, timeouts, group membership, and recovery.
- [ ] Alerts distinguish health degradation from process liveness failure.

## 17. Self-Practice Questions

1. Why can a single `DOWN` contributor cause aggregate health to be `DOWN`?
2. How do component details help narrow down the root cause?
3. How does overall health differ from readiness/liveness?
4. Why should a database outage not fail liveness by default?
5. How do health group include/exclude settings affect the aggregate?
6. What two distinct things do `StatusAggregator` order and HTTP mapping handle?
7. What causes can make the DB indicator `DOWN` even though business queries still work?
8. Why does a custom `HealthIndicator` need a bounded timeout?
9. When should readiness depend on a remote service?
10. How do you distinguish a 401/403 probe error from a `DOWN` component?
11. Why shouldn't you change status mappings to hide a `DOWN` state?
12. Which cases should be tested before deploying Kubernetes probes?

## References

- [Spring Boot 3.5 — Health Endpoint](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Spring Boot 3.5 — Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)

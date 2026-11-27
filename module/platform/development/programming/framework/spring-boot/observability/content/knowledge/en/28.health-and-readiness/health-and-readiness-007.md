# Database Health

A Spring Boot application can keep running normally even when the database loses connectivity, runs out of connections, or rejects authentication. If a load balancer keeps routing traffic to an instance unable to serve database-backed requests, users will receive errors even though the Java process is still alive. A database health indicator lets Actuator check database accessibility and include that state in the health response; readiness probes can use this information to decide whether the instance should receive traffic.

The **Database health** lesson belongs to the **Health and readiness** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; understand context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

> **Core takeaway:** Database health reflects the ability to check the database at probe time. It does not replace metrics/traces for measuring latency or investigating queries. Distinguish liveness (whether the process needs a restart) from readiness (whether the instance should receive traffic). A database dependency typically affects the readiness of services that rely on it; putting the database into liveness without careful thought can let an outage trigger a fleet-wide restart loop.

## 1. Learning objectives

After this lesson, you will be able to:
1. Explain the role of the database health indicator in Spring Boot Actuator.
2. Understand `DataSourceHealthIndicator` and how health contributors check the database.
3. Interpret UP, DOWN, OUT_OF_SERVICE, and UNKNOWN statuses.
4. Distinguish liveness, readiness, and overall application health.
5. Decide when the database should affect readiness.
6. Configure health groups and probe endpoints.
7. Understand the impact of timeouts, connection pools, and database outages on health checks.
8. Protect health details so JDBC URLs, database versions, or sensitive exceptions are not exposed.
9. Test database health when the DB is available, unreachable, or slow to query.
10. Combine health with metrics, logs, and traces during incident investigation.

## 2. What is a database health indicator?

Spring Boot Actuator provides a health endpoint that aggregates `HealthContributor`s. For a JDBC `DataSource`, auto-configuration can register a database health indicator when a `DataSource` and appropriate health auto-configuration are present.

The database health indicator checks database accessibility through the `DataSource`/connection. It usually borrows a connection and executes validation/a query appropriate for the implementation. If the check succeeds, the component reports UP; if it fails, the component can report DOWN along with error details depending on configuration and detail-visibility permissions.

~~~http
GET /actuator/health
~~~

Illustrative response when the database is healthy:

~~~json
{
  "status": "UP",
  "components": {
    "db": {"status": "UP"},
    "diskSpace": {"status": "UP"}
  }
}
~~~

The response when the database check fails may look like:

~~~json
{
  "status": "DOWN",
  "components": {
    "db": {"status": "DOWN"}
  }
}
~~~

This is an abbreviated example; the actual response depends on health details visibility, health groups, and the Spring Boot version.

## 3. What does DataSourceHealthIndicator check?

`DataSourceHealthIndicator` is the health contributor for a JDBC `DataSource`. It verifies that the application can interact with the database over the connection it uses.

Depending on the database/driver and Spring Boot version, the indicator can:
- Obtain a connection from the `DataSource`.
- Use a validation query or JDBC Connection validation.
- Include database product/version in details when configured and permitted to be shown.
- Return DOWN when a connection cannot be obtained/validated or the check query fails.

Do not treat a health check as a comprehensive measurement of the database. A simple query succeeding does not prove all business queries are fast, indexes are optimal, transactions are healthy, or replicas are caught up.

### 3.1 Validation query

Normally auto-configuration chooses a validation method suited to the driver. If a database/driver requires a specific query, you can configure an appropriate bean/custom `HealthIndicator` or datasource validation mechanism. Do not use heavy queries or queries on large business tables as health probes.

~~~yaml
management:
  health:
    db:
      enabled: true
~~~

This property enables/disables the database health contributor in supported Spring Boot configurations. Check the exact property reference for your version when changing behavior.

### 3.2 How the connection pool affects results

The health check uses the application's `DataSource`; if the pool runs out of connections, the probe can fail even though the database server is still alive. That is still an important signal: the instance currently cannot obtain a connection to serve traffic.

During investigation, distinguish between database unreachable, invalid credentials/permissions, pool exhausted, connection validation timeout, and overloaded database.

## 4. Health statuses

Spring Boot `Health` status typically uses these values:

| Status | Meaning |
|---|---|
| UP | Checked component is working |
| DOWN | Component failed or did not pass the check |
| OUT_OF_SERVICE | Component is intentionally taken out of service |
| UNKNOWN | Status cannot be determined |

`HealthAggregator`/`StatusAggregator` aggregates component statuses into a top-level status. By default, DOWN and OUT_OF_SERVICE usually have precedence that prevents the overall status from being UP; status order can be customized.

The database contributor being DOWN can make overall `/actuator/health` DOWN. However, the readiness group can be configured separately; not every contributor is automatically included in every group.

## 5. Liveness and readiness differ

| Probe | Question | What does the platform usually do on failure? |
|---|---|---|
| Liveness | Is the process still progressing and not stuck to the point of needing a restart? | Restart container/process |
| Readiness | Is the instance ready to accept new traffic? | Temporarily stop routing traffic to the instance |
| Overall health | What state are the application's health contributors in? | Used for diagnostics/monitoring |

A database outage usually does not mean the JVM needs to restart. If the database is inside liveness, all pods can fail liveness simultaneously and restart repeatedly, placing extra load on the DB when it recovers.

For readiness, the answer depends on architecture:
- If all critical requests require the DB, DB DOWN can make the instance not ready.
- If the service can serve partial functionality via cache/fallback, readiness can stay UP while returning controlled errors for DB-dependent features.
- If only one route/feature relies on a secondary database, you do not necessarily need to pull the whole service out of the load balancer.

Set policy based on actual serving capability, not merely dependency state.

## 6. Spring Boot probe health groups

Spring Boot can expose liveness and readiness health groups. In Kubernetes, probe paths are typically:
- `/actuator/health/liveness`
- `/actuator/health/readiness`

Enable probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Spring Boot creates the corresponding health groups in supported environments. You can explicitly add the database to the readiness group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
~~~

This example places the application readiness state and the database health contributor into the readiness group. Verify existing group members and actual contributor names; if using multiple `DataSource`s, contributor names may differ.

Do not add `db` to the liveness group out of habit. Liveness should focus on the internal state of the process/application, not depend on external services that can fail independently.

## 7. When should the database affect readiness?

Use questions framed around business capabilities:

1. Can the instance receive requests and return valid results if the DB is unavailable?
2. Is there a cache/fallback/read-only mode for part of the requests?
3. Are there endpoints that do not need the DB yet should continue serving?
4. Is the DB a mandatory dependency for all traffic or just one feature?
5. During a DB outage, does pulling instances from the load balancer reduce errors or leave the entire fleet with zero instances?
6. When the DB recovers, does readiness recover automatically?

Examples:
- Order Service requires the DB to create orders: the DB can be placed in readiness.
- Catalog Service has a full cache and tolerates stale data: readiness can follow its own policy.
- Notification Service consumes messages and writes to another durable queue: a secondary reporting database need not determine readiness.

Readiness is a routing decision; it does not fix a broken dependency. If all replicas depend on the same DOWN database, all of them may become not-ready. That may be correct for data integrity, but it must be factored into your incident strategy.

## 8. Health details and security

Health details can disclose database product/version, JDBC URL or host/port if added by custom indicators, exception class/message, component names and dependency topology, pool state, or internal infrastructure information.

Configure details visibility for authenticated users:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      roles: ACTUATOR
~~~

Do not enable `show-details=always` on public endpoints. Protect management endpoints with Spring Security, network policies, and an appropriate management port. Never include credentials or raw exception messages in custom `Health` details.

### 8.1 Safe custom health details

If details are needed, return only useful, normalized data, such as dependency alias `primary-db`, check `connection-validation`, `error.type` `connection_timeout`, and an appropriate timestamp.

Avoid raw JDBC URLs, usernames, passwords, SQL, query parameters, and stack traces. Access-controlled logs/traces are the appropriate place for detailed diagnostics.

## 9. Timeouts and health check frequency

Health checks also generate load on the database. If the orchestrator calls readiness every few seconds across hundreds of instances, each probe can acquire a connection and run validation. When the DB is overloaded, frequent health probes can make matters worse.

Considerations:
- Short, bounded connection acquisition/validation timeouts.
- Reasonable probe intervals; avoid overly tight polling.
- Failure thresholds and success thresholds to avoid flapping.
- Never run heavy business queries.
- Never allow probes to wait indefinitely.
- Ensure probes do not hold connections for long.
- Monitor health check latency and failure rate.

If a health check times out due to pool exhaustion, that is a signal the instance cannot acquire a connection. Do not raise timeouts indefinitely just to make the probe green while the application actually cannot serve traffic.

## 10. Multiple DataSources and database health

An application can have multiple `DataSource`s: primary, reporting, audit, or tenant-specific. Default health contributors may be created for each datasource depending on naming/auto-configuration. Check component names in `/actuator/health` instead of assuming there is only one `db`.

Readiness policy should answer:
- Is Primary DB mandatory while reporting DB is optional?
- Does an unavailable Audit DB block all requests?
- Can one feature degrade while the rest continues serving?
- Can tenant database health be checked in aggregate without generating excessive probes?

Do not run a health check for every tenant/database on every probe if the count is large. Doing so can cause a connection storm and slow down the endpoint. Use an aggregation strategy, sampling, or dependency status from an appropriate management system.

## 11. Custom HealthIndicator

When logic different from the default `DataSource` check is needed, you can write a dedicated `HealthIndicator`. Illustrative example using a dependency client configured with a timeout:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("primaryDatabase")
class PrimaryDatabaseHealthIndicator implements HealthIndicator {

    private final DatabaseProbe probe;

    PrimaryDatabaseHealthIndicator(DatabaseProbe probe) {
        this.probe = probe;
    }

    @Override
    public Health health() {
        try {
            probe.checkConnection();
            return Health.up()
                    .withDetail("dependency", "primary-db")
                    .build();
        } catch (RuntimeException ex) {
            return Health.down()
                    .withDetail("dependency", "primary-db")
                    .withDetail("error.type", "connection_failure")
                    .build();
        }
    }
}
~~~

`DatabaseProbe` is an illustrative abstraction. In production code, use a connection/validation check API with a timeout, and do not swallow errors to return UP. A custom contributor may change the component name; avoid accidentally running two checks hitting the same DB if the default indicator remains enabled.

### 11.1 Do not return DOWN for every business error

A `HealthIndicator` checks dependency serving capability, not whether a sample business transaction succeeds. A unique constraint violation or request validation error is not evidence that the database is unhealthy. Only include errors in health results that reflect dependency availability/capability.

## 12. Combining database health with metrics, logs, and traces

Health reports status at probe time. Metrics reveal trends and magnitude. Traces/logs show the cause of individual calls.

| Signal | Question |
|---|---|
| Health | Is the DB check currently UP or DOWN? |
| Metrics | Are connection errors, pool pending count, or query latency rising? |
| Logs | What are the exception class/SQLState and error timestamp? |
| Traces | Which requests are waiting on the DB, and how long do query spans take? |

When readiness is DOWN:
1. Check HikariCP active/idle/pending metrics.
2. Inspect database connection error/timeout counters.
3. Open logs around the timestamp to inspect SQLState class/exception type.
4. Search for traces with slow or errored DB spans.
5. Identify whether it is a DB outage, pool exhaustion, or permission/credential issue.

Do not use the health endpoint as a latency dashboard; probes usually reflect only a tiny check, not real workload queries.

## 13. Testing database health

| Scenario | Expected result |
|---|---|
| Database reachable, validation succeeds | `db` UP |
| Database server stopped or network blocked | `db` DOWN |
| Wrong credentials | `db` DOWN and error classified safely |
| Connection pool exhausted | Check may go DOWN/timeout per pool behavior |
| Slow validation query | Check times out/fails per policy |
| Primary DB UP, reporting DB DOWN | Separate component statuses and overall/group per policy |
| DB DOWN while service has fallback | Readiness follows defined business capability |
| Liveness probe when DB is DOWN | Remains UP if process is healthy and policy does not depend on DB |

### 13.1 Integration testing

You can use Testcontainers to run a real database for integration tests. Tests should:
- Initialize the application context with a `DataSource`.
- Call the `HealthContributor`/Actuator health endpoint.
- Confirm the `db` component is UP.
- Stop or block the database and confirm DOWN.
- Verify readiness/liveness health groups per configuration.
- Verify details do not contain JDBC credentials or raw exception messages.

If a test stops a container, use an explicit lifecycle and avoid tests sensitive to tight timing.

## 14. Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| `/actuator/health` returns DOWN | Database check failed or another component is DOWN | Read component status and authorized details |
| `db` DOWN while DB server is still UP | Pool exhausted, credentials, validation, or network path | Check pool metrics and connection test from app |
| Readiness DOWN stops traffic to all pods | DB included in readiness of every replica | Verify policy and degradation capability |
| Liveness DOWN during DB outage | External dependency attached to liveness | Remove DB from liveness group |
| Health endpoint is slow | Probe query/connection acquisition waiting too long | Set timeouts and use lightweight validation |
| Health flapping | Overly sensitive probe interval/threshold or flaky DB | Tune thresholds and check latency/error rates |
| Details not visible | `show-details` policy or authorization | Use an authorized role; do not enable public details |
| Multiple `db` components | Multiple `DataSource`s | Identify which contributor is critical |
| Probes create a connection storm | Many instances/tenant checks polling too fast | Reduce frequency, aggregate, and limit concurrency |
| Health UP yet business queries fail | Probe only checks a basic connection | Combine query metrics, traces, and application-level SLOs |

## 15. Playbook: Database DOWN in readiness

**Scenario:** Kubernetes readiness probes begin failing across multiple Order Service pods.

1. Check `/actuator/health/readiness` and the `db` component status.
2. Confirm whether the database has a real outage or the application cannot obtain connections from the pool.
3. Inspect pool active/idle/pending metrics, connection timeouts, and query latency metrics.
4. Check logs by normalized SQLState/exception type.
5. Open traces near the start of the failure to pinpoint connection, validation, or query paths.
6. Verify whether the DB contributor was intentionally included in the readiness group.
7. Evaluate whether the service can serve requests without the DB or must stop receiving all traffic.
8. Avoid restarting all pods if the liveness process is still healthy and the DB is an external dependency.
9. Restore the database/pool/network/credentials according to root cause.
10. Verify readiness returns to UP, probes are not flapping, and request error rates drop.

When the DB recovers, do not scale all consumers/pods simultaneously if doing so creates a connection storm. Use controlled recovery and monitor pool saturation.

## 16. Self-check exercises

**Exercise 1 — HealthIndicator.** What does `DataSourceHealthIndicator` check? Why does UP not prove business queries are fast?

**Exercise 2 — Liveness vs readiness.** Should a database outage fail liveness? Explain the consequences if every pod restarts simultaneously.

**Exercise 3 — Readiness policy.** A service has a full cache for GET requests but requires the DB for POST requests. How would you decide readiness?

**Exercise 4 — Pool exhaustion.** The database server is still UP yet `db` health is DOWN. Why could the pool be the cause?

**Exercise 5 — Security.** Why should `show-details=always` not be set on a public management endpoint? Name sensitive details that could be exposed.

**Exercise 6 — Multiple DataSources.** Primary DB is UP while reporting DB is DOWN. How do you decide which component affects readiness?

**Exercise 7 — Probe load.** Why can overly frequent health checks worsen a database outage?

**Exercise 8 — Observability signals.** When readiness is DOWN, list the metrics, logs, and traces to examine to distinguish a DB outage from pool exhaustion.

### Answer hints

1. Checks ability to acquire/validate a connection. It does not measure full query plans, locks, or workload latency.
2. Usually no; liveness failures can cause a restart loop and increase load when the DB recovers.
3. Define capability: if instances can still serve GET accurately using the cache, readiness can stay UP per policy; POST returns controlled errors or routes separately.
4. No free connections left in the pool, connections held too long/leaked, or max pool size too small; the app cannot borrow a connection even though the DB server is alive.
5. Can expose host/JDBC URL, version, exception messages, and topology. Use auth/network restrictions and `show-details=when-authorized`.
6. Only the DB required for core traffic should affect readiness; reporting DB can be optional if the feature can degrade.
7. Each probe may open a connection/query; many replicas probing simultaneously add extra load to the DB.
8. Pool active/idle/pending, connection errors/timeouts, SQLState logs, and DB client spans/latency.

## 17. Official references

- [Spring Boot — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health): health endpoint, contributors, and status aggregation.
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): liveness/readiness groups and probe behavior.
- [Spring Boot — Health Groups](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health.groups): configuring group members and statuses.
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html): `LivenessState`, `ReadinessState`, and availability lifecycle.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): datasource/pool metrics and Micrometer integration.
- [Spring Security — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/web/spring-security.html): authentication/authorization for management endpoints.
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): probe semantics and restart/routing behavior.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP): pool sizing, connection acquisition, and timeout configuration.

**Key takeaways:** A database health indicator checks database accessibility via `DataSource` at probe time. Readiness can depend on the DB if an instance cannot serve properly when the DB is unavailable; liveness should generally reflect internal process health to avoid restart loops. Protect health details, configure sensible probe timeouts/frequencies, and combine health with pool metrics, logs, and DB traces to pinpoint root causes.

# Distinguishing Health Checks, Readiness, and Real-Load Capacity

In a Spring Data Relational R2DBC application, a health endpoint returning `UP` does not mean the system can reliably serve every request or sustain production load. A health check typically confirms that basic components are functioning at check time. Readiness answers whether an instance should receive traffic right now. Real-load capacity must be evaluated through latency, throughput, error rates, connection pool utilization, database resources, and testing under representative load.

These three concepts are related but serve distinct purposes. If a heavy database query is used as a liveness probe, Kubernetes may restart entire pods when the database slows down, even though the process is alive and restarting cannot fix the root cause. If readiness only checks whether the process has started, a pod may receive traffic before the R2DBC pool or schema is ready. If capacity is judged solely from a health endpoint, the system can report `UP` while the pool is nearly exhausted and real requests are timing out.

Spring Boot Actuator provides health contributors and probe groups such as liveness and readiness. In reactive applications, health indicators can return `Mono<Health>`. R2DBC also requires monitoring connection acquisition, query latency, pool saturation, timeouts, cancellations, and driver errors. Health endpoints should be short, cheap, and bounded by timeouts; load capacity must be evaluated via metrics, tracing, load tests, and SLOs.

## 1. Three Different Questions

| Concept | Question to Answer | Consumer of Result | Example |
| --- | --- | --- | --- |
| Health check | Is a component or application in a basic working state? | Monitoring, operators, dashboards | Actuator `/actuator/health` |
| Readiness | Should this instance receive new requests right now? | Load balancer, Kubernetes Service/Ingress, orchestrator | `/actuator/health/readiness` |
| Real-load capacity | Does the system meet real workload demands within latency/error/capacity limits? | SRE, operations, capacity planning, release gates | Load tests, metrics, traces, SLOs |

A process can be alive yet not ready: the application may be running migrations, warming up required caches, or waiting to establish required connections. A process can also be ready to accept traffic yet lack capacity for a sudden spike. Conversely, a probe can fail due to a transient dependency disruption where restarting the process brings no benefit.

Health checks are status signals. Readiness is a traffic-routing decision. Capacity is a property of the whole system under a defined workload and observation window. Do not use a single endpoint to substitute for all three.

## 2. What Is a Health Check?

A health check is a tightly scoped check determining whether an application or dependency can perform a basic operation. In Spring Boot, Actuator aggregates status from `HealthIndicator` or `ReactiveHealthIndicator` beans.

A health check can verify:

- The application context has initialized.
- A required dependency is reachable.
- The database accepts a lightweight test query.
- An essential messaging or cache system is accessible.
- An internal state published by the application.

Health checks are typically point-in-time checks, not comprehensive functional tests. For instance, a successful `SELECT 1` proves a connection can execute a simple SQL statement at that moment. It does not prove every business query, table, permission, transaction, or concurrent request will succeed.

### Health Statuses in Spring Boot

Actuator commonly uses these statuses:

| Status | General Meaning |
| --- | --- |
| `UP` | The checked component is operating according to the indicator's criteria |
| `DOWN` | The component is not functioning or the check failed |
| `OUT_OF_SERVICE` | The component has been explicitly marked out of service |
| `UNKNOWN` | Insufficient information to determine status |

The aggregated endpoint status depends on the status aggregator and mapping configuration. With common default HTTP settings, `DOWN` and `OUT_OF_SERVICE` map to HTTP 503; `UP` returns HTTP 200. Check `management.endpoint.health.status.http-mapping` if your application customizes mappings.

### A Health Endpoint Is Not a Business Endpoint

Do not turn a health endpoint into an API executing full business workflows—such as creating and deleting an order, sending real messages, or calling multiple external services. Those operations have side effects, consume resources, and can worsen an ongoing incident.

A good health check has these traits:

- Fast and bounded by a finite timeout.
- Little or no side effects.
- Reads no large datasets.
- Clear UP/DOWN criteria.
- Returns no secrets, connection strings, or sensitive data.
- Generates negligible load when polled repeatedly by multiple probes.

## 3. Liveness: Is the Process Alive and Able to Keep Running?

Liveness answers: is the process still functioning in a way where restarting would help recover it? With Spring Boot, availability states can expose liveness via `LivenessState`.

Liveness should generally reflect internal process health:

- The application has not been marked `BROKEN`.
- The runtime can still handle basic tasks.
- No unrecoverable internal state exists where a restart is the right remedy.

Liveness should not depend directly on the database, Redis, message brokers, or external APIs. If the database drops connections briefly, restarting all pods usually does not help the database recover. If all pods restart simultaneously, they can trigger a connection storm right as the database is recovering.

### Why Exclude the Database from Liveness?

Suppose the database undergoes 30 seconds of maintenance. If liveness executes `SELECT 1` and returns DOWN, Kubernetes may restart the pods. Once the database recovers, many pods boot together, initialize new pools, and open connections simultaneously, potentially overloading the database further.

Liveness should detect stuck processes or broken internal states that require a restart. External dependencies should be handled via readiness/metrics/alerts according to an appropriate policy.

## 4. Readiness: Should the Instance Receive Traffic?

Readiness answers: if a load balancer sends a new request to this instance right now, can the instance handle the requests it is responsible for?

An instance that is not yet ready may be:

- Initializing required components.
- Running necessary warm-up steps.
- Missing required credentials/configuration.
- Disconnected from a database required for most requests.
- Draining ahead of shutdown.
- Explicitly marked `REFUSING_TRAFFIC`.

When readiness fails, the orchestrator or load balancer stops routing new traffic to that instance per its health-check mechanism. The process remains alive and can continue background work or finish in-flight requests.

### Readiness Depends on the Instance's Role

Not every dependency belongs in readiness. If a service only needs Redis on a few endpoints and serves most requests fine without Redis, putting Redis in readiness can take down an otherwise useful instance. If the database is mandatory for every critical request, readiness may need to reflect database status.

Determine:

1. Which requests is the instance expected to serve?
2. Which dependencies are mandatory for those requests?
3. If a dependency fails, does the application have a valid fallback or degraded mode?
4. If all instances lose a dependency at once, does marking every instance unready help?
5. Do probes have suitable timeouts and frequencies?

Readiness should reflect traffic acceptance capability per the service's contract, not the health of every system the application knows about.

## 5. Startup Probes and Startup Duration

Startup probes solve slow-booting applications. When Kubernetes uses a startup probe, liveness and readiness probes are not evaluated normally until the startup probe succeeds.

Startup probes are helpful when an application:

- Initializes a large Spring context.
- Runs mandatory initialization steps.
- Loads metadata or configuration from external sources.
- Warms up required components before serving.
- Has startup times that vary across environments.

Do not inflate liveness `failureThreshold` just to tolerate slow startups when a startup probe is the proper mechanism. Startup and liveness serve different purposes: startup covers initialization time; liveness detects stuck processes after startup.

Spring Boot provides availability states and Actuator probe groups for liveness/readiness. Kubernetes startup probes can target the liveness endpoint or a startup-specific health endpoint depending on deployment configuration.

## 6. Spring Boot Actuator and Probe Groups

Add Actuator to a Spring Boot application to expose health endpoints:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
```

Or Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

In environments requiring Kubernetes probes, enable probe support and declare groups explicitly:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
```

Commonly used endpoints:

| Endpoint | Purpose |
| --- | --- |
| `/actuator/health` | Aggregated health |
| `/actuator/health/liveness` | Liveness probe |
| `/actuator/health/readiness` | Readiness probe |

In Kubernetes, Spring Boot may enable probe support automatically upon detecting a Kubernetes environment in supported versions. Explicit configuration keeps deployments readable and verifiable. Verify exact property names and behavior against your project's Spring Boot version.

### Exposing Probe Paths on the Application Port

If management endpoints run on a separate port, Kubernetes might probe the management port successfully while the main server port stops accepting traffic properly. You can enable additional probe paths on the main server port:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

Spring Boot exposes `/livez` and `/readyz` on the application port when this feature is supported. Verify the actual endpoints exposed by your version and point probes at the same port serving application traffic.

Never expose all Actuator endpoints publicly just so Kubernetes can read health. Expose only needed endpoints, restrict network access, and protect endpoints holding operational details.

## 7. Should Readiness Include the R2DBC Database?

Spring Boot can auto-configure a database health contributor when it detects a matching `ConnectionFactory`/R2DBC driver. In many configurations, the database component ID is `db`; check `/actuator/health` and component names in your actual application version.

If the database is a mandatory dependency to serve requests, you can include the database component in the readiness group:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
```

In this configuration:

- Liveness reflects the process's availability state.
- Readiness reflects the availability state and the database contributor's status.
- A `DOWN` database contributor marks the readiness group `DOWN` and returns a non-success HTTP status per status mapping.

Only include `db` in readiness if the database is truly mandatory for serving traffic. If the service has a degraded mode or only certain endpoints need the database, consider a more precise indicator or readiness policy.

### What Does the `db` Health Contributor Check?

The database health indicator typically runs a lightweight connection/validation check per Spring Boot and driver implementation. It does not run full business queries, measure throughput, or verify load capacity. How connections are acquired, validation queries, and timeouts can vary by version.

If a specialized check is needed, implement a custom `ReactiveHealthIndicator` for that dependency. Avoid adding a second query check if the built-in contributor already satisfies the goal.

## 8. Custom Reactive Health Indicator for R2DBC

When you need to check a more specific condition than the built-in contributor provides, implement `ReactiveHealthIndicator`. The following example runs a lightweight query with a timeout:

```java
import java.time.Duration;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("r2dbcReadiness")
public class R2dbcReadinessHealthIndicator
        implements ReactiveHealthIndicator {

    private final DatabaseClient databaseClient;

    public R2dbcReadinessHealthIndicator(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Override
    public Mono<Health> health() {
        return databaseClient.sql("SELECT 1")
                .fetch()
                .first()
                .map(row -> Health.up().build())
                .switchIfEmpty(Mono.just(
                        Health.down()
                                .withDetail("reason", "No result returned")
                                .build()
                ))
                .timeout(Duration.ofSeconds(2))
                .onErrorResume(error -> Mono.just(
                        Health.down()
                                .withDetail("cause", error.getClass().getSimpleName())
                                .build()
                ));
    }
}
```

This is an illustrative example for Spring Boot Actuator and Spring Data R2DBC; align imports/APIs with your version. `DatabaseClient.fetch().first()` returns a publisher with the first row; `SELECT 1` normally returns one row. If the source is empty or the query errors/times out, the indicator returns `DOWN`.

Add the custom indicator to the readiness group:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,r2dbcReadiness
```

If the built-in `db` contributor already meets your requirements, do not add a duplicate custom indicator. Running two checks concurrently adds unnecessary connections and queries.

### Keep Health Checks Lightweight

Never use queries such as:

```sql
SELECT COUNT(*) FROM orders;
```

or scan large tables to check database liveness. Such queries consume far more resources than needed and can aggravate ongoing incidents. Health queries should verify basic connectivity and execution, not run reports.

### Never Return Sensitive Information

The example above only puts the exception class name into details. Avoid returning full messages if they might expose hostnames, schemas, SQL, usernames, paths, or sensitive details. Configure detail visibility to restrict access to authorized users.

## 9. An R2DBC Health Check Does Not Prove Pool Capacity

A passing `SELECT 1` only proves one connection could be acquired and executed under current conditions. It does not prove the pool has enough connections for the full workload.

For example, suppose a pool has `maxSize = 30`. The health check acquires one connection and finishes. Meanwhile, 30 business requests may be holding all remaining connections; subsequent requests wait or time out. Health can still return `UP` if the probe snags a connection or runs during a brief gap.

Conversely, when the pool is momentarily full, a health check may wait on acquire and time out even though the process is alive. This can be a useful readiness signal if the service truly cannot take more traffic, but avoid overly sensitive probes that cause instances to flap ready/unready on brief fluctuations.

Track separately:

- Allocated connections vs. configured max limit.
- Acquired/in-use connections.
- Idle connections.
- Pending acquire requests.
- Acquire wait times and acquire timeout rates.
- Connection hold durations.
- Query latency and concurrent query counts.

Specific metric names depend on R2DBC Pool, Micrometer, and Spring Boot versions. Inspect your application's metric registry rather than assuming identical names across versions.

## 10. Readiness Is Not a Capacity Test

A probe typically executes a single lightweight request on a timer with minimal payload. It does not represent production workloads. Therefore, readiness `UP` does not prove:

- 100, 1,000, or 10,000 concurrent requests can be handled.
- P95/P99 latency stays within SLOs.
- The database has enough CPU/I/O for peak hours.
- The connection pool has headroom under peak load.
- No lock contention or slow queries exist.
- Consumers/background jobs can keep up with incoming data rates.
- The system remains stable over hours or days.

Real-load capacity must be evaluated with production-like workloads and sustained observation metrics. Probes are merely status signals for orchestrators.

### Capacity Spans Multiple Layers

With R2DBC, capacity is not just maximum connection count:

1. **HTTP server:** concurrent requests, event loops, queues, and timeouts.
2. **Reactor pipeline:** concurrency, prefetch, scheduler usage, and cancellations.
3. **R2DBC pool:** connection acquire, idle, pending, and max size.
4. **Database:** CPU, IOPS, locks, transactions, buffer/cache, and query plans.
5. **Other dependencies:** HTTP services, caches, brokers, and storage.
6. **Application runtime:** heap, direct memory, GC, CPU, and thread/scheduler saturation.

Any single layer can become a bottleneck even while every basic health check reports `UP`.

## 11. Key Metrics for Spring Data R2DBC

To know whether the application can handle real load, monitor both requests and the database.

### HTTP/Application Metrics

- Request rate by endpoint and method.
- Error rate by status and exception category.
- P50/P95/P99 latency.
- In-flight requests and queue lengths if applicable.
- Timeouts, cancellations, and client disconnects.
- Successful throughput, not just incoming request count.

### R2DBC Pool Metrics

- Max and allocated connection counts.
- In-use connection count.
- Idle connection count.
- Pending acquire count.
- Acquire latency and acquire timeouts.
- Connection usage duration.

When `r2dbc-pool` is used, verify metrics and registry configuration. Never infer pool health merely because the database health indicator is `UP`.

### Database Metrics

- Query latency by query type or operation.
- Slow query count.
- Transaction duration and rollback rate.
- Lock waits/deadlocks.
- CPU, memory, disk I/O, and storage pressure.
- Active connections vs. server connection limits.
- Replication lag if replicas are used.
- Query plan regressions and index usage.

### Reactor/Runtime Metrics

- Scheduler queue/worker saturation if instrumented.
- Appropriate Reactor operator metrics.
- Heap/direct memory and GC pauses.
- Container CPU throttling.
- Blocked event loops or accidental blocking work.
- Active publishers and completion times.

Never expose all metrics on public endpoints. Use a Micrometer registry and a proper monitoring system; cap label cardinality and avoid putting customer IDs, request IDs, or free-form strings into labels.

## 12. Using Spring Boot Actuator for Observability

Actuator provides health and metrics endpoints. Example exposure in an administrative environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
      show-components: when_authorized
```

`prometheus` requires adding the matching registry dependency. Exposure settings must align with your Spring Boot version and security policy. Expose only necessary endpoints; metrics can disclose topology, operation names, and traffic characteristics.

Typical endpoints:

- `/actuator/health`: aggregated status.
- `/actuator/health/liveness`: liveness status.
- `/actuator/health/readiness`: readiness status.
- `/actuator/metrics`: inspect Micrometer-registered meters.
- `/actuator/prometheus`: Prometheus scrape format when the registry is present.

Health details should only be visible to authorized callers. Never return passwords, URLs with credentials, SQL bind values, or sensitive exception messages.

## 13. What Should the Readiness Group Include?

A well-designed readiness group includes only conditions truly needed for an instance to accept traffic.

Example of an R2DBC service requiring the database for most requests:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
```

Example of a service that can handle read-only requests when an optional dependency disconnects:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
```

In the second case, if the database is still required for most requests, keeping it in readiness makes sense. If only one endpoint depends on the database while other features remain functional, consider basing readiness on overall service capability or splitting services/traffic classes instead of pulling the entire instance out of rotation.

### Do Not Include Every Dependency Mechanically in Readiness

Suppose a service uses:

- A mandatory R2DBC database.
- Redis purely as a cache with database fallback.
- An analytics API used solely for asynchronous event delivery.
- An email provider outside the request path.

Readiness may only need to check the mandatory database. If Redis goes down, the service may slow down yet keep serving; analytics or email outages should not stop the service from taking traffic. Instead, alerts and retry/outbox mechanisms handle optional dependencies.

### Shared Dependency Outage

If a shared database goes `DOWN`, all instances may transition to readiness `DOWN` simultaneously. That accurately reflects their inability to serve DB-backed requests, yet can leave load balancers with zero backends and cause gateway errors. Coordinate readiness with alerting, fallbacks, maintenance policies, and degraded-mode handling.

Do not remove the database from readiness solely to keep probes green. Decide based on actual service capability and the routing impact when a dependency fails.

## 14. Readiness State and Application Lifecycle

Spring Boot uses availability states to represent whether an application is ready to accept traffic. Common states include:

- `ACCEPTING_TRAFFIC`: the application can accept traffic.
- `REFUSING_TRAFFIC`: the application should not receive new requests.

Applications can publish availability events to actively transition readiness, such as draining before shutdown:

```java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC
);
```

When ready to accept traffic again:

```java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.ACCEPTING_TRAFFIC
);
```

Imports and `ApplicationContext` injection should match your application structure. Spring Boot updates availability states automatically during standard lifecycles; publish manual events only when specific business/operational conditions require controlling readiness.

### Graceful Shutdown

When an application receives a shutdown signal:

1. Transition readiness to `REFUSING_TRAFFIC` to stop new requests.
2. Give the load balancer/orchestrator time to update endpoint routing.
3. Drain in-flight requests within the configured graceful shutdown window.
4. Close publishers/consumers and the connection pool cleanly.
5. Terminate the process.

Closing the `ConnectionFactory` too early can fail in-flight requests. Accepting new requests while shutting down the pool can cause timeouts. Readiness and graceful shutdown must be designed together.

## 15. Kubernetes Liveness, Readiness, and Startup Probes

Example Kubernetes configuration using Actuator endpoints:

```yaml
containers:
  - name: app
    image: example/r2dbc-service:1.0
    ports:
      - name: http
        containerPort: 8080
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 10
      failureThreshold: 30
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3
```

This is an example container configuration in a Pod spec; adjust values for your service's startup time, normal latency, and recovery targets. If additional paths are enabled on the main port, `/livez` and `/readyz` can be used instead of management paths.

### Parameter Meanings

| Parameter | Meaning |
| --- | --- |
| `periodSeconds` | Interval between probes |
| `timeoutSeconds` | Maximum time to wait for one probe |
| `failureThreshold` | Consecutive failures before taking action |
| `successThreshold` | Consecutive successes needed to transition to success where applicable |
| `initialDelaySeconds` | Wait time before the first probe if configured |

Startup probes allow slower startup without premature liveness restarts. Readiness can poll more frequently than liveness since its goal is traffic routing. Set timeouts long enough for normal conditions without leaving pods in an unknown state too long.

## 16. Management Port vs. Main Application Port

A common setup runs Actuator on a dedicated port, e.g., `management.server.port: 8081`, while the application receives traffic on 8080. If Kubernetes probes only port 8081, the management server can still report healthy even if the main application port is failing or failed to bind.

When possible, expose additional health paths on the main port or verify the main server with an appropriate probe. The goal is for readiness/liveness to reflect the exact instance receiving load-balancer traffic.

Example:

```yaml
server:
  port: 8080
management:
  server:
    port: 8081
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

Verify the exact paths and ports exposed in your Spring Boot version. Ensure firewalls/network policies allow kubelet to reach probe paths without exposing Actuator to the public Internet.

## 17. Health Check Timeouts and Frequency

A health check without a timeout can hang indefinitely when the pool or database runs into trouble. Bound probe timeouts at both the HTTP/Kubernetes layer and the reactive operation layer.

With a custom R2DBC indicator:

```java
return databaseClient.sql("SELECT 1")
        .fetch()
        .first()
        .map(row -> Health.up().build())
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(error -> Mono.just(
                Health.down()
                        .withDetail("cause", error.getClass().getSimpleName())
                        .build()
        ));
```

The publisher timeout caps how long the pipeline waits for connection/query execution. Kubernetes' `timeoutSeconds` caps the HTTP probe wait time. Coordinate the two: the internal timeout should be short enough for the indicator to respond before kubelet aborts the request.

### Avoiding Probe Storms

If 100 pods each query the database multiple times per second, health checks can create unnecessary load. Pick a reasonable `periodSeconds`, an ultra-lightweight query, and consider health endpoint caching TTLs if supported by your version/configuration. Never run heavy aggregate queries or call multiple external dependencies on every probe.

Health checks should represent a tiny fraction of real traffic load. During an outage, they must never make database pressure worse.

## 18. Health Checks and Circuit Breakers

Health checks, readiness, and circuit breakers are related but do not replace each other.

- Health checks provide status signals to monitoring and orchestrators.
- Readiness controls whether an instance receives new traffic.
- Circuit breakers govern calls to a dependency when error rates or latency cross thresholds; they can open, half-open, and close.
- Retries re-attempt operations per attempt/backoff policy.
- Bulkheads limit concurrency or resources allocated to a dependency.

For example, when the database slows down, a service-layer circuit breaker can stop requests from piling up waiting queries. Readiness can turn `DOWN` if the application is genuinely unable to serve. Never use health endpoints to replace circuit breakers in individual request paths.

## 19. Distinguishing Probes from Synthetic Monitoring

Synthetic monitoring executes representative user journeys or requests from outside the system to test user experience. Examples:

- Sending a login request with a test account.
- Reading a fixture record through the API.
- Executing a test transaction that can roll back or uses test data.
- Exercising the API through real DNS, TLS, gateway, and authentication.

Synthetic checks can uncover routing, auth, serialization, or business query failures that `SELECT 1` misses. However, they also require rate limits, test data isolation, and side-effect controls. Never turn a complex synthetic journey into a continuous liveness probe.

Health checks typically run inside the cluster to check instance state; synthetic monitoring tests paths from the client's perspective. Both complement each other.

## 20. Evaluating Real-Load Capacity

To know whether an R2DBC service can sustain production load, run representative workloads and measure outcomes. Common test types:

| Load Test Type | Purpose |
| --- | --- |
| Load test | Verify expected load under normal conditions |
| Stress test | Push load past expected levels to find limits and degradation behavior |
| Spike test | Introduce sudden traffic bursts to observe system response |
| Soak test | Hold steady load for extended periods to detect memory leaks, pool leaks, or gradual degradation |
| Capacity test | Find maximum throughput while meeting latency/error targets |

A test that merely blasts requests without measuring latency, errors, and resource consumption cannot prove capacity.

### Workloads Must Be Representative

Build scenarios close to production:

- Similar read/write ratios.
- Similar payload sizes and returned row counts.
- Similar tenant/customer distributions and query selectivity.
- Similar cache hit/miss ratios.
- Similar transaction durations and data contention levels.
- Realistic concurrency and arrival rates.
- External dependencies simulated with realistic latency/errors.
- Replica counts and pool sizes close to deployment configs.

Benchmarking only `SELECT 1` does not represent APIs executing multi-table joins or multi-entity write transactions.

## 21. SLOs, Latency, and Error Rates

Real-load capacity should be judged against clear service objectives, such as:

- Successful request ratio within a time window.
- P95/P99 latency for critical endpoints.
- Timeout and database error rates.
- Successful throughput under expected load.
- Recovery time after dependency failures.
- Connection pool utilization and headroom.

For example, a service may report health `UP` while P99 latency degrades from 200 ms to 8 seconds. Process-wise, it is alive; user-experience-wise, it is violating SLOs. Health and SLOs answer different questions.

Base alerts on SLOs/error budgets and saturation metrics rather than alerting only when `/actuator/health` reports `DOWN`. A system can degrade severely long before a health indicator fails.

## 22. R2DBC Pool Saturation Is a Key Signal

An R2DBC pool caps connection count. When all connections are acquired, new requests must wait for one to be released. If wait time exceeds `maxAcquireTime` or the request deadline, the operation may time out.

Signs of pool saturation:

- `acquired` stays near `maxSize` for extended periods.
- `pending` rises.
- Acquire latency rises.
- Frequent acquire timeout errors.
- Database query latency looks normal while request latency rises due to pool waiting.
- Connection usage duration grows because transactions/streams hold connections too long.

Distinguish two cases:

1. **Slow database:** queries genuinely take a long time, keeping connections leased longer.
2. **Pool too small or concurrency too high:** requests wait for connections even though database queries are reasonably fast.

Enlarging pool size can help if the database has spare capacity and the pool is the bottleneck. However, if the database is already saturated, enlarging the pool allows more concurrent queries and can worsen latency. Measure both pool and database before tuning.

## 23. R2DBC Query Latency and Transaction Duration

A lightweight health check can pass while business queries suffer due to:

- Missing indexes or query plan changes.
- Full table scans on large tables.
- Lock waits or deadlocks.
- Many transactions holding connections too long.
- Large payloads and CPU-heavy mapping.
- N+1 queries or excessive round-trips.
- Network latency between app and database.
- Database running backups, vacuum/maintenance, or competing workloads.

Track query latency by normalized operation name or repository method. Never use full SQL or parameter values as metric labels due to cardinality and sensitive data risks. Distributed tracing can link request spans to database spans when supported by driver/instrumentation.

Long transactions also strain pools and the database. Avoid making HTTP calls, sending emails, or waiting on user input while holding an R2DBC transaction unless strict consistency demands it.

## 24. Readiness When the Database Disconnects

Define the desired behavior intentionally rather than blindly marking unready in every case.

### Database Mandatory for All Requests

If most endpoints read/write the database with no valid fallback, readiness can include the database contributor. When the database is `DOWN`, instances stop accepting new traffic; separate alerts report the dependency outage.

### Database Serves Only Part of the Functionality

If the service can still serve health/info, cache-backed reads, or independent endpoints, you may not want to remove the entire instance from load balancing. Alternatives include splitting features into separate services or exposing explicit degraded modes for DB-dependent endpoints.

### Brief Database Errors While Pool Can Recover

Overly sensitive probes can cause readiness flapping. Pick suitable timeouts and failure thresholds, use circuit breakers or backpressure on request paths, and alert on error rates. Never let one slow query trigger an immediate process restart.

### Shared Database Outage

If all replicas go unready simultaneously, the load balancer may return no-backend errors. That does not restore the database. Have dependency-level observability and runbooks instead of relying on pod restarts.

## 25. Readiness During Deployments and Rolling Updates

During a rolling deployment, a new instance should not receive traffic until:

- The application context finishes starting.
- Mandatory beans are ready.
- Database connectivity and schema are compatible.
- Essential initialization/warm-up finishes.
- Readiness state transitions to `ACCEPTING_TRAFFIC`.

Old instances should transition to `REFUSING_TRAFFIC` before stopping so the load balancer halts new requests. In-flight requests should drain within the allowed grace period.

### Backward-Compatible Schema Migrations

When multiple application versions run concurrently during deployment, follow expand-and-contract schema migrations:

1. Add new columns/indexes in a way compatible with the old version.
2. Deploy application code capable of reading/writing the new schema while staying compatible with the old version.
3. Backfill data if needed.
4. Shift traffic and verify the new version is stable.
5. Remove legacy columns/structures in a later release.

Readiness should pass only when the instance can genuinely serve against the current schema. Never use health checks to run heavy migrations every few seconds; migrations belong in deployment lifecycles or controlled jobs.

## 26. Securing Health Endpoints

Health endpoints can leak:

- Which database or broker is in use.
- Component and dependency names.
- Exception types, hostnames, or connection details.
- Pool state and internal topology.
- Versions or deployment metadata.

Principles:

- Expose only needed endpoints.
- Restrict access via network policies, firewalls, or Spring Security.
- Use `show-details: when_authorized` if details are needed.
- Never include credentials, tokens, SQL parameters, or user data in health details.
- Never let health endpoints trigger arbitrary writes or side effects.
- Use simple endpoints for kubelet and detailed endpoints for authorized monitoring.

Kubernetes needs to poll probe endpoints from cluster nodes/agents, which does not mean those endpoints should be public on the Internet.

## 27. Combined Example Configuration for an R2DBC Service

The example below enables probes, keeps liveness independent of the database, and includes the database in readiness assuming the service requires the DB for core requests:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db:5432/app
    username: app_user
    password: ${DB_PASSWORD}

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: when_authorized
      show-components: when_authorized
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
```

The PostgreSQL URL illustrates an R2DBC application; swap URL/driver for your actual database. `prometheus` requires the matching registry dependency. The `db` component must exist among health contributors in the application context; if missing, check driver/auto-configuration or use a clearly named custom indicator.

Do not copy a readiness config containing `db` for every service blindly. If the database is optional for traffic or degraded mode exists, tailor the group to your actual service contract.

## 28. Common Design Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Pods restart repeatedly during DB outage | Liveness depends on database | Keep liveness for internal process state; put dependencies in readiness/alerting |
| Pod receives traffic before app is ready | Readiness only checks process or probe misconfigured | Check readiness state and mandatory dependencies |
| `/actuator/health` is `UP` yet API times out | Health check too shallow; pool or queries saturated | Monitor pool, latency, error rate, and run load tests |
| Readiness flaps continuously | Probe timeout too low or flaky dependency | Tune timeouts/thresholds, reduce probe load, address dependency |
| All replicas evicted when cache fails | Optional dependency included in readiness | Include only dependencies required for core traffic |
| Management port `UP` yet app port broken | Probes check separate management server only | Use additional paths on main port or probe serving port directly |
| Health checks overload the DB | Heavy query or excessive probe frequency | Use lightweight query, timeout, and sensible period |
| Readiness `UP` despite pool near exhaustion | Single probe still obtains a connection | Track acquired/pending/acquire latency and capacity separately |
| Probe timeouts hold requests open long | Indicator lacks internal timeout | Set reactive timeout and matching HTTP probe timeout |
| Health details leak sensitive info | Public `show-details` or raw exception messages | Enforce authorization and sanitize details |
| Restarts fail to fix dependency errors | Using liveness for external DB/broker failures | Alert and handle dependency issues; avoid restart storms |
| Load test passes yet production bottlenecks | Unrepresentative test workload or missing soak/spike tests | Match production traffic mix, concurrency, data volume, and duration |

## 29. Observability and Probe Design Workflow

1. Define what question each health check answers and who consumes it.
2. Design liveness independently of external dependencies; report only internal process states requiring restart.
3. Configure startup probes for slow-starting applications when needed.
4. Identify mandatory dependencies for accepting traffic and include them in readiness with clear criteria.
5. For R2DBC, verify the built-in `db` contributor or write a lightweight, timeout-bounded custom reactive indicator.
6. Ensure probes target ports/paths representing the traffic-serving server.
7. Tune timeouts, periods, and failure thresholds to avoid probe storms and flapping.
8. Monitor HTTP latency/errors, R2DBC pool, query latency, database saturation, and runtime metrics.
9. Build load/stress/spike/soak tests using production-like workloads and data.
10. Evaluate P95/P99, error rates, throughput, pool headroom, and database capacity against SLOs.
11. Coordinate readiness with graceful shutdown, rolling deployments, and compatible schema migrations.
12. Secure health/metrics endpoints and restrict details to authorized users.

## 30. Takeaways

- Health checks verify a basic condition at check time; they do not prove full business correctness or capacity.
- Liveness answers whether the process needs a restart to recover; avoid depending on databases or external services.
- Readiness answers whether an instance should receive new traffic; include only dependencies mandatory for core traffic.
- Startup probes give applications time to initialize before liveness/readiness take full effect.
- Spring Boot Actuator provides health contributors and probe groups; configure `livenessState` and `readinessState` explicitly.
- The R2DBC database contributor checks basic connectivity/validation; a passing `SELECT 1` does not prove business query performance or pool capacity.
- Custom `ReactiveHealthIndicator`s should return timeout-bounded publishers with lightweight queries and sanitized health details.
- Readiness `UP` does not mean a service can handle real load; monitor latency, error rates, throughput, pool saturation, and database metrics.
- Reactive Streams backpressure, R2DBC pooling, and database capacity are distinct layers requiring separate observation.
- Load, stress, spike, and soak tests use representative workloads to evaluate capacity and endurance.
- Readiness, graceful shutdown, and rolling deployments must work together to avoid receiving traffic while draining.
- Secure health endpoints; never expose credentials, SQL parameters, or sensitive exception messages.

A well-operated R2DBC service requires three distinct forms of evidence: the process is alive, the instance is ready for traffic, and the system sustains workload within SLO limits. Use liveness to govern restarts, readiness to govern routing, and metrics/tracing/load testing to evaluate real-load capacity. Keep probes lightweight and bounded by timeouts; observe connection pools, queries, and the database separately so you catch degradation before health endpoints ever turn `DOWN`.

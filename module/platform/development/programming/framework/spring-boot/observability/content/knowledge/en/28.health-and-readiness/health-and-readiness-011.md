# Readiness When Dependencies Fail in Spring Boot

**Readiness when dependencies fail** is how a Spring Boot application decides whether an instance is still eligible to receive new requests when a database, message broker, or supporting service experiences an outage. Readiness reflects the ability to serve traffic at the current moment; liveness reflects whether the process is still running and able to continue or needs restarting. Separating these two signals helps the system avoid mass restarts when a shared dependency is disrupted.

In the **SPRING_BOOT_OBSERVABILITY** module, health indicators and Actuator provide data to orchestration, load balancers, and operators. This lesson belongs to the **Health and readiness** chapter and focuses on readiness semantics during dependency failures, classifying mandatory vs. optional dependencies, fail-open/fail-closed policies, health groups, Kubernetes probes, timeouts/circuit breakers, testing, and recovery procedures.

## 1. What question does readiness answer?

Readiness answers: **should this instance receive additional new traffic right now?**

An instance may be:
- Running normally while the primary database is unreachable.
- Still serving read-only endpoints while the message broker is failing.
- Started up yet still completing warm-up or loading configuration.
- Draining for deployment or shutdown.
- Overloaded and temporarily should not receive new requests.

Readiness is not a general health score. It is a traffic-routing decision based on the instance's serving capability and workload requirements.

### 1.1. Distinguishing liveness, readiness, and startup

| Probe | Question | On failure |
| --- | --- | --- |
| Liveness | Is the process still alive and making progress? | Orchestrator may restart container |
| Readiness | Can the instance accept traffic? | Remove instance from endpoints/load balancing |
| Startup | Has the application finished starting up? | Defer liveness/readiness until startup succeeds |

A dependency outage should generally affect readiness when the dependency is essential for requests to be served. It should not automatically fail liveness, because restarting the application will not fix a downed database or shared broker.

### 1.2. Example scenario

An order service depends on a primary database and emits events to Kafka:
- Primary database down: if all business requests need the database, the instance can become not ready.
- Kafka down: if requests still save orders successfully and events are written to an outbox for later publishing, the service can remain ready.
- Cache down: if a database fallback exists and latency stays within SLO, the service can remain ready.
- Optional analytics API down: need not affect readiness.

Decisions must rest on actual serving capability and business contracts, not solely on whether a dependency reports health DOWN.

## 2. Classifying dependencies before adding to readiness

Do not lump all dependencies into one health aggregate and use that aggregate as readiness. First, classify by role.

| Dependency type | Example | Readiness impact |
| --- | --- | --- |
| Critical synchronous | Database needed for most requests | Usually affects |
| Critical authentication | Identity provider if every request requires live verification | Depends on token validation/cache/fallback |
| Deferred/asynchronous | Broker when using transactional outbox | May not affect |
| Optional enhancement | Cache with fallback | Usually does not affect if fallback meets SLO |
| Analytics/telemetry | Analytics sink, tracing backend | Usually does not affect |
| External feature-specific | Payment provider used on only one route | May affect only that route/traffic class |

Readiness is typically an instance-level signal, whereas a dependency might impact only a subset of features. If a dependency serves only a rarely used endpoint, removing the whole instance from the load balancer reduces availability for still-working endpoints.

### 2.1. Criticality based on the request path

Map out:
1. Request types the service serves.
2. Which dependencies lie on the synchronous path of each request.
3. Whether a cache/fallback/outbox/local queue exists.
4. Whether fallback latency still satisfies the SLO.
5. When the dependency fails, whether a meaningful response can still be returned.

Readiness should reflect the core requests the instance commits to serving. Do not equate every dependency in the application context with a mandatory dependency.

## 3. Fail-closed and fail-open

When a dependency cannot be verified, the application needs an explicit policy.

- **Fail-closed:** treat an unknown/unhealthy dependency as not ready.
- **Fail-open:** remain ready if the application has a fallback or can still serve core functionality.

| Situation | Potentially suitable policy | Reason |
| --- | --- | --- |
| Primary database cannot serve business requests | Fail-closed | Instance cannot complete core work |
| Cache unreachable yet DB fallback is stable | Fail-open | Service can still serve |
| Broker failing yet outbox stores events durably | Fail-open | Publishing can be processed later |
| Tracing backend failing | Fail-open | Telemetry outage should not stop business traffic |
| Optional dependency for a single feature | Feature-dependent | Can keep instance ready for other routes |

Fail-open does not mean ignoring failures. Metrics, alerts, and fallback behaviors are needed so operators know which capabilities are degraded.

Fail-closed is not always safe either. If all instances check a downed database and go not ready simultaneously, the load balancer may have zero backends left. That may be appropriate if no requests can be served, but its impact must be understood and restart loops avoided.

## 4. Configuring health groups in Spring Boot

Spring Boot Actuator supports health groups to create separate health views, such as readiness and liveness. Depending on version and configuration, probe groups may be created automatically in Kubernetes or configured explicitly.

Example exposing health:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
```

Common paths:
- `/actuator/health/liveness`
- `/actuator/health/readiness`

Check actual paths if management base path or management port has changed. Do not assume default endpoint paths always exist across every version/configuration.

### 4.1. Customizing the readiness group

You can define the readiness group and select appropriate health contributors:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include:
            - readinessState
            - db
        liveness:
          include:
            - livenessState
```

Contributor names like `db` depend on auto-configuration and whether the application has the corresponding health indicator. With R2DBC, messaging, or custom dependencies, contributor IDs may differ. Check the actual health endpoint rather than copying non-existent IDs.

The readiness group example above treats the database as a mandatory dependency. If the database has an outage, readiness can become DOWN. Do not include broker/cache/telemetry in the group merely because they have health indicators.

## 5. ReadinessState and ApplicationAvailability

Spring Boot provides `ApplicationAvailability` and `AvailabilityState` to describe application availability status. Two key states are usually central:
- `LivenessState`: `CORRECT` or `BROKEN`.
- `ReadinessState`: `ACCEPTING_TRAFFIC` or `REFUSING_TRAFFIC`.

Applications can transition readiness state when starting to drain or when operational conditions mean the instance should not accept traffic.

Example publishing readiness state:

```java
@Component
class TrafficAvailability {

    private final ApplicationEventPublisher events;

    TrafficAvailability(ApplicationEventPublisher events) {
        this.events = events;
    }

    void stopAcceptingTraffic() {
        events.publishEvent(
                new AvailabilityChangeEvent<>(
                        this,
                        ReadinessState.REFUSING_TRAFFIC));
    }

    void acceptTraffic() {
        events.publishEvent(
                new AvailabilityChangeEvent<>(
                        this,
                        ReadinessState.ACCEPTING_TRAFFIC));
    }
}
```

This illustrates Spring Boot's availability API. Import `AvailabilityChangeEvent` and `ReadinessState` from the packages corresponding to your version. Never alter liveness state merely because a remote dependency fails.

## 6. HealthIndicator for mandatory dependencies

Spring Boot Actuator can aggregate health contributors. For custom dependencies, implement `HealthIndicator` or `ReactiveHealthIndicator` depending on the application.

Example synchronous health indicator:

```java
@Component
class CriticalCatalogHealthIndicator implements HealthIndicator {

    private final CatalogClient catalogClient;

    CriticalCatalogHealthIndicator(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @Override
    public Health health() {
        try {
            catalogClient.checkAvailability();
            return Health.up().build();
        }
        catch (Exception ex) {
            return Health.down()
                    .withDetail("dependency", "catalog")
                    .withDetail("reason", "unavailable")
                    .build();
        }
    }
}
```

Do not put exception messages, URLs with credentials, or payloads into health details. The example intentionally checks one dependency; do not call multiple slow APIs on every probe.

For reactive applications, use `ReactiveHealthIndicator` and a reactive client to avoid blocking the event loop. Never call `block()` inside a WebFlux health indicator.

### 6.1. Timeouts for health checks

Health checks require short, finite timeouts. If a probe waits indefinitely on a dependency, Kubernetes may continuously time out and fail to receive readiness signals.

Timeouts must be smaller than the probe time budget and short enough not to place heavy load on an outaged dependency. Use appropriate client timeouts/circuit breakers; do not issue a new unbounded health request on every kubelet poll.

## 7. Dependency failures should not fail liveness

Liveness should generally rely on internal process state: whether the application context is active, whether event loops/threads are progressing, and whether the application is free of severe deadlocks under the chosen check.

If the database goes down:
- Readiness can go DOWN if the database is needed for core requests.
- Liveness remains UP if the process is operating normally.
- The orchestrator stops sending new traffic to the instance.
- When the database recovers, readiness can return UP without restarting the application.

If database health is tied to liveness, all pods may restart simultaneously while the database is still down. Once the database recovers, a restart storm can cause a connection surge and prolong the outage.

Do not use liveness as a mechanism to force applications to self-restart when remote dependencies are unhealthy.

## 8. Optional dependencies and degraded readiness

A service can serve partial functionality when a dependency fails. Some strategies:

1. **Stay ready:** if fallbacks satisfy contracts and SLOs.
2. **Whole instance not ready:** if most critical requests cannot be served.
3. **Split workloads:** deploy endpoints/workers with different dependency profiles as separate workloads.
4. **Readiness by traffic class:** use routing architectures supporting traffic-class separation rather than cramming every condition into an instance-level boolean.

Basic Kubernetes readiness is a pod/container-level signal. It does not route individual endpoints separately by dependency. If only the payment route is broken while order lookup still works, marking the whole pod not ready cuts off both traffic types.

### 8.1. Degraded is not a standard probe state

An application can maintain an internal `DEGRADED` state, though probes usually need to return pass/fail per orchestrator contract. You can expose degraded details separately to operators via a health group or metrics, while readiness makes decisions under a clear policy.

## 9. Broker failures, outbox, and asynchronous dependencies

A message broker often does not sit on the synchronous response path if the application uses a transactional outbox or persists work to the database before publishing.

Example:
1. Request creates an order and writes both order + outbox record in the same transaction.
2. HTTP response succeeds after commit.
3. Background publisher sends outbox events to the broker.
4. Broker is temporarily unavailable; outbox retains events for retry.
5. Service can still accept order requests while the database operates and outbox capacity holds.

In this architecture, a broker outage may not fail readiness immediately. Instead, monitor:
- Outbox backlog.
- Oldest message age.
- Publish failure/retry rate.
- DLQ count.
- Estimated backlog drain time.

If the broker is a mandatory processing path with no durable fallback, readiness policy may differ. Decide based on application semantics.

## 10. Cache, identity providers, and external APIs

Not every dependency belongs in readiness.

**Cache:** if the cache is down yet the database fallback meets latency/throughput requirements, maintain readiness and emit cache degradation alerts.

**Identity provider:** if tokens are verified offline using a cached public key, an identity provider outage may not affect current requests. If every request requires live introspection, this dependency may be critical.

**External API:** if only one feature relies on an API, you do not necessarily need to mark the entire service not ready. Use circuit breakers, fallbacks, and per-feature metrics.

Readiness should express serving capability per contract, not an aggregation of every system the service connects to.

## 11. Circuit breakers and health checks

A circuit breaker protects the application from calling a continuously failing dependency. However, an open circuit breaker does not automatically mean the instance must be not ready.

If fallbacks work, readiness can remain UP. If a core operation lacks a fallback and every request fails, readiness can go DOWN.

Avoid routing health checks through the circuit breaker in a way that makes probes mutate breaker state or generate extra requests during an outage. Health checks should reflect needed state via lightweight, timed-out, side-effect-free checks.

## 12. Kubernetes probe configuration

Example Pod spec:

```yaml
containers:
  - name: app
    image: example/order-service:1.0
    ports:
      - name: http
        containerPort: 8080
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2
    startupProbe:
      httpGet:
        path: /actuator/health
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 30
```

Values are examples. Startup probe path must suit the health group and app startup behavior. When using a separate management port, probes must reach the right port/path; do not bind the management server to localhost only if kubelet needs access over the pod network.

### 12.1. How does a readiness failure affect traffic?

When a readiness probe fails, Kubernetes marks the Pod not ready and typically removes the Pod from endpoints used to route Service traffic. The container continues running; kubelet does not restart the container solely for a readiness failure.

When readiness recovers, the Pod can be re-added to endpoints. Propagation to load balancers/service meshes can take time; the application still needs to handle graceful draining and open connections.

### 12.2. Startup probe

A startup probe gives applications with long startups time without being prematurely restarted by the liveness probe. It does not replace readiness; once startup succeeds, readiness continues deciding whether the instance is ready to accept traffic.

## 13. Avoiding health checks that overload dependencies

Kubernetes may call probes multiple times per pod. If every probe opens multiple connections/queries or calls several external APIs, health checking can worsen an outaged dependency.

Principles:
- Use lightweight probes and short timeouts.
- Check only genuinely critical dependencies.
- Avoid heavy queries or data scans.
- Never run long retry loops inside a health check.
- Consider caching results briefly if semantics allow.
- Limit concurrency of dependency checks.
- Never invoke health checks per user request.

Cached health results must have a clear TTL and understood stale behavior. If an UP result is cached too long, readiness may continue reporting healthy after a dependency fails; if TTL is too short, probes may generate heavy load. Pick TTL based on failure detection objectives.

## 14. Readiness, autoscaling, and cascading failures

When a shared dependency suffers an outage, if all application pods go not ready at once:
- The service may have zero endpoints remaining.
- Autoscalers may scale up pod counts due to backlog/CPU, adding extra connections to the dependency when it recovers.
- Misconfigured liveness may restart all pods.
- Retry traffic may concentrate onto remaining instances and overload them.

Coordinate readiness with circuit breakers, bounded retries, connection pool limits, rate limiting/load shedding, autoscaling signals, backpressure, and recovery ramp-up.

Readiness is not the sole mechanism to protect the system. It controls traffic routing to instances; dependency protection requires multiple layers.

## 15. Testing readiness when dependencies fail

Testing must verify readiness and liveness behavior when dependencies actually fail, not just test an isolated `HealthIndicator`.

### 15.1. Testing the health indicator

Mock dependencies returning success/failure/timeout. Verify health results and sanitized details.

### 15.2. Integration testing with Spring Boot

Use the Spring context and Actuator endpoints to verify:
- Readiness group contains expected contributors.
- Critical dependency DOWN causes readiness DOWN.
- Optional dependency DOWN does not cause readiness DOWN.
- Liveness remains UP when remote dependencies fail.
- Health details do not expose credentials or exception messages.

### 15.3. Testing outage and recovery

Use Testcontainers or a controllable mock dependency that can stop/start:
1. Start the application and dependency.
2. Confirm readiness is UP.
3. Stop the critical dependency.
4. Confirm readiness goes DOWN within the expected detection window.
5. Confirm liveness stays UP and the process does not restart.
6. Restart the dependency.
7. Confirm readiness recovers to UP.

For optional dependencies, verify readiness stays UP while degradation metrics/logs are recorded.

## 16. Troubleshooting readiness when dependencies fail

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Pods restart repeatedly during DB outage | DB health put in liveness | Separate liveness from remote dependencies |
| Pods still receive traffic while critical DB is down | Readiness group lacks DB indicator | Check group `include` and contributor ID |
| Pods not ready when cache is down despite fallback | Cache treated as critical | Review dependency classification |
| All pods not ready simultaneously | Shared dependency outage or overly strict probe | Review policy and fallbacks |
| Readiness probe timeout | Health check calls slow dependency or lacks timeout | Bound timeouts and number of checks |
| Readiness flapping | Fluctuating dependency health or unsuitable TTL | Check latency and caching policy |
| Readiness UP yet requests fail | Probe checks only process or wrong dependency | Compare request path with readiness policy |
| Readiness stays DOWN long after DB recovery | Cached state, unrecovered pool, or broken indicator | Check TTL, pool, and health logs |
| Health checks overload the DB | Heavy query or overly frequent probes | Use lightweight checks, reduce frequency/concurrency |
| Broker outage makes service not ready | Broker included in aggregate despite outbox | Check async fallback and backlog |
| Management endpoint unreachable | Wrong port/path/bind address | Check probe port and base path |
| Health details leak data | `show-details` too permissive | Sanitize and restrict authorization |

### Investigation workflow

1. Inspect Pod events and status of each probe.
2. Verify probes call the correct management port/path.
3. Read readiness and liveness separately.
4. Identify which health contributor makes readiness DOWN.
5. Correlate that dependency with request paths and fallbacks.
6. Check timeouts, latency, pool saturation, and circuit breakers.
7. Confirm liveness does not depend on remote dependencies.
8. Inspect autoscaling, retries, and traffic distribution during the outage.
9. Once the dependency recovers, monitor readiness, pools, and error rates.
10. Adjust policy and re-test both outage and recovery.

## 17. Practice: simulating a database outage

The goal is to prove a database outage changes readiness without causing liveness to restart the application.

### Preparation

- Spring Boot Actuator application.
- Lab database that can be stopped/started.
- Readiness/liveness groups.
- Kubernetes or a probe simulation environment.
- Metrics/logs to observe health transitions.

### Step 1 — Configure health probes

Enable Actuator probes and expose the health endpoint. Verify liveness/readiness paths work.

### Step 2 — Add the database to readiness

Add the database contributor to the readiness group if the database is a mandatory dependency on the request path.

### Step 3 — Keep liveness independent

Ensure the liveness group contains only liveness state and truly needed process-local checks.

### Step 4 — Verify initial state

Start the app/database. Call both health paths and confirm both are UP.

### Step 5 — Induce an outage

Stop the lab database or block connections in a controlled way. Confirm readiness switches to DOWN within the timeout budget.

### Step 6 — Check the process

Confirm liveness stays UP and the container does not restart solely due to the database outage.

### Step 7 — Check traffic

Confirm the not-ready instance is removed from service endpoints while the process stays running to recover.

### Step 8 — Recover the database

Restart the database. Monitor the connection pool, readiness, and request success rate.

### Step 9 — Test an optional dependency

Simulate an optional cache/broker outage. Confirm readiness remains UP if fallback/outbox still meets contract.

### Step 10 — Acceptance

Record outage detection time, readiness transitions, liveness state, recovery time, and traffic impact.

### Acceptance checklist

| What to prove | Expected result |
| --- | --- |
| Probe semantics | Distinguish startup, liveness, readiness |
| Dependency classification | Critical and optional classified |
| Readiness | Critical outage marks not ready per policy |
| Liveness | Remote dependency outage does not restart process |
| Fallback | Optional outage still serves core functions |
| Timeout | Health checks have finite deadlines |
| Traffic routing | Not-ready instance removed from endpoints |
| Recovery | Readiness returns UP after recovery |
| Security | Health details leak no secrets |
| Load | Probes do not create heavy load on dependencies |
| Operations | Metrics/logs exist for degraded state |
| Testing | Outage and recovery tests exist |

## 18. Principles to remember

1. **Readiness decides traffic intake; liveness decides whether the process needs restarting.** Do not mechanically treat dependency outages as liveness failures.
2. **Put only critical dependencies into readiness.** Optional dependencies with fallbacks should not take the whole instance out of traffic.
3. **Classify by request path and business contract.** A dependency may be critical for one feature yet optional for the rest.
4. **Fail-open/fail-closed must be intentional.** Weigh fallbacks, SLOs, and the impact of all replicas going not ready together.
5. **Health checks must be lightweight and have timeouts.** Probes must not worsen a dependency outage.
6. **A broker outage may not affect readiness if a durable outbox exists.** Track backlog and publish delay separately.
7. **Separate health groups.** Liveness reflects the process; readiness reflects traffic-serving capability.
8. **Readiness is not the only protection mechanism.** Combine with circuit breakers, bounded retries, rate limits, and backpressure.
9. **Test both outage and recovery.** Ensure readiness recovers without unnecessary restarts.
10. **Track degraded states separately.** An instance remaining ready may still be degraded in one feature; metrics and alerts must reflect that.

Readiness when dependencies fail must reflect an instance's actual ability to serve requests. By classifying dependencies along the request path, keeping liveness independent of remote systems, setting timeouts on health checks, and testing outages/recovery, Spring Boot can coordinate with Kubernetes to stop sending traffic to unservable instances while giving processes a chance to recover once dependencies come back online.

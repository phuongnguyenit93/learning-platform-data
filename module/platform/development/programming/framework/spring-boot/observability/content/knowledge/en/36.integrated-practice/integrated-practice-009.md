# Configuring Health and Readiness

A Spring Boot service may start successfully yet still not be ready to serve requests. The application might be loading caches, initializing connections, running migrations, or waiting on a mandatory component. Conversely, an application already serving requests can encounter an internal failure and require a restart. Checking only whether the process is alive makes it hard for the deployment platform to distinguish between these two situations.

Spring Boot Actuator provides health endpoints and availability states to describe application status. When running on Kubernetes, a liveness probe indicates whether the container needs to be restarted; a readiness probe indicates whether the Pod should receive traffic; and a startup probe gives slow-starting applications time to initialize. Configuring these three checks properly helps orchestrate traffic and recover from incidents without creating unintended restart loops.

This practice exercise builds a health and readiness configuration for a Spring Boot service with an HTTP API, a database, and an external dependency. You will enable health probes, create health groups, configure Kubernetes probes, test state transitions, and correlate results with metrics, logs, and distributed tracing.

## 1. Distinguishing Liveness, Readiness, and Startup

The three probes answer three different questions:

| Probe | Question | What Does Kubernetes Do on Failure? | Example |
|---|---|---|---|
| Liveness | Is the application still alive and able to make forward progress? | Restarts the container after reaching the failure threshold | Deadlock, blocked event loop, or stalled main worker |
| Readiness | Is the Pod ready to receive requests? | Marks the Pod unready and stops routing service traffic to it | Warming up cache or required dependency unavailable |
| Startup | Has the application finished initial startup? | Holds off liveness/readiness until startup succeeds; exceeding threshold restarts container | Application needs extended time to load data or initialize |

Liveness must not depend on a database, message broker, or external service. If the database experiences an outage, all Pods could simultaneously fail liveness and get restarted. Mass restarts do not fix the database and instead add load as applications boot back up, creating a worse recovery loop.

Readiness may check a dependency if the service genuinely cannot serve requests when that dependency is down. However, consider degraded modes, caches, or retry capabilities before adding a dependency to readiness. A system may still serve most requests when a secondary integration fails; in that case, marking the entire Pod unready can unnecessarily reduce serving capacity.

A startup probe is useful when startup times can be long or variable. It lets you set a dedicated startup threshold without loosening the liveness probe for the entire container lifetime. Once the startup probe succeeds, liveness and readiness begin running per their configurations.

## 2. Enabling Health Probes in Spring Boot

Suppose the application already includes Spring Boot Actuator and serves HTTP on port `8080`. With Maven, the dependency typically looks like:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

In `application.yaml`, enable probes and expose the health endpoint:

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
        add-additional-paths: true
      show-details: when-authorized
```

When `management.endpoint.health.probes.enabled` is enabled, Spring Boot provides two health groups for liveness and readiness. These group endpoints can be accessed via:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

With `management.endpoint.health.probes.add-additional-paths=true`, Spring Boot also exposes two short paths on the main HTTP port:

```text
GET /livez
GET /readyz
```

These short paths are very helpful when Kubernetes checks the application through its request-serving port. If you configure the management server to run on a separate port, pay special attention to checking readiness and liveness on the main application port. A management server still responding does not prove the user-facing HTTP server is healthy.

`show-details: when-authorized` restricts detailed health information to authorized callers. Kubernetes probes only need the HTTP status code and overall status; they do not need database connection info, internal hostnames, or other sensitive details.

## 3. Defining Health Group Contents

Spring Boot provides availability state contributors:

- `livenessState` reflects the application's liveness state.
- `readinessState` reflects whether the application is accepting or refusing traffic.

By default, the liveness group is built around `livenessState`, and the readiness group around `readinessState`. You can declare them explicitly and add required health indicators to readiness:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
```

In this example, `db` is the health indicator created by Spring Boot auto-configuration when the application has a configured datasource and matching dependencies. Readiness transitions to unready only when the availability state refuses traffic or the database health contributor reports an error.

Only include `db` if the API genuinely cannot serve requests when the database is unavailable. If certain endpoints can still serve from cache or local data, consider designing readiness around actual serving capability. Avoid adding every dependency to readiness out of habit. Each probe can invoke health contributors; dependency checks must be fast, bounded by timeouts, and avoid heavy load.

Do not include `db`, brokers, or remote APIs in the liveness group. Liveness should reflect the progress capability of the application process itself. When an external dependency fails, the application needs a chance to keep running, log the condition, and recover connections.

## 4. Writing a Custom HealthIndicator for a Critical Dependency

If you need to check a dependency that has no built-in health contributor, implement `HealthIndicator`. The example below illustrates an external inventory service:

```java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("inventory")
class InventoryHealthIndicator implements HealthIndicator {

    private final InventoryClient client;

    InventoryHealthIndicator(InventoryClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            // Client must be configured with short, bounded connect/read timeouts.
            client.checkConnection();
            return Health.up().withDetail("dependency", "inventory").build();
        } catch (Exception ex) {
            // Do not put tokens, internal URLs, or sensitive info into details.
            return Health.down().withDetail("dependency", "inventory").build();
        }
    }
}
```

`InventoryClient` is an application component and should be replaced with your actual client. The check method must enforce explicit timeouts; never let a health request hang indefinitely when an external service stops responding. If the API can still serve requests during a temporary inventory outage, do not add `inventory` to readiness.

If inventory is a mandatory dependency, add the contributor to the readiness group:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db,inventory
```

The contributor ID is set from the bean name `inventory`. You can inspect the contributor individually at `/actuator/health/inventory` if the health endpoint and contributor are exposed under appropriate configuration. For production, only allow authorized users to view health details; platform probes should call the aggregated readiness endpoint.

A health indicator should perform minimal checks of serving ability. Never run heavy queries, full table scans, sequential multi-API calls, or write operations on every probe. If deep checks are needed, provide a separate access-controlled diagnostic endpoint and run it on a schedule or during incident investigation.

## 5. Configuring Kubernetes Probes

When using `/livez` and `/readyz` on the application port, part of a Deployment manifest might look like:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: observability-demo
spec:
  replicas: 3
  selector:
    matchLabels:
      app: observability-demo
  template:
    metadata:
      labels:
        app: observability-demo
    spec:
      containers:
        - name: app
          image: example/observability-demo:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
```

The timing values above are illustrative starting points. With this startup probe configuration, Kubernetes gives the application up to roughly 300 seconds of startup checks before treating the container as failed, depending on period and timeout calculation. Once startup succeeds, liveness and readiness begin executing. Choose thresholds based on actual startup time and environmental latency.

Readiness is polled more frequently in the example because its goal is steering traffic when serving state changes. Liveness can have a longer period to avoid restarts caused by transient hiccups. `failureThreshold` combined with `periodSeconds` determines the approximate window before Kubernetes acts; `timeoutSeconds` caps how long each check can wait.

When readiness fails, the Pod keeps running but is marked unready and removed from Service endpoints until the probe passes again. When liveness exceeds its failure threshold, kubelet restarts the container. The startup probe gives the application time to initialize before the other two probes begin.

If you do not use `add-additional-paths`, configure probes to call `/actuator/health/liveness` and `/actuator/health/readiness`. Ensure `management.server.port`, `management.server.base-path`, context path, and port name in the Deployment match the actual endpoints.

## 6. Coordinating Readiness with Graceful Shutdown

During a rolling deployment or scale-down, the application needs to stop accepting new requests and finish in-flight requests. Spring Boot supports graceful shutdown for the web server:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

When shutdown starts, Spring Boot transitions readiness to refusing traffic so the platform can stop routing new requests to the instance. The web server then waits for in-flight requests to complete within the configured timeout. Align this duration with the Pod's `terminationGracePeriodSeconds` and ingress/load balancer drain times.

If the application performs asynchronous warm-up after the Spring context is ready, the default readiness state may switch to accepting traffic before warm-up completes. In that case, manage `ReadinessState` explicitly:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.stereotype.Component;

@Component
class StartupReadiness {

    private final ConfigurableApplicationContext context;

    StartupReadiness(ConfigurableApplicationContext context) {
        this.context = context;
    }

    void beginWarmup() {
        AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC);
    }

    void finishWarmup() {
        AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
```

Call `beginWarmup()` before starting warm-up tasks and only call `finishWarmup()` once serving prerequisites are ready. In a real application, tie these two calls to a clear lifecycle or initialization workflow; avoid leaving readiness in refusing state without a recovery path.

Readiness state is also useful when placing an instance into maintenance mode. Switch to `REFUSING_TRAFFIC`, wait for traffic to drain, perform maintenance, then switch back to `ACCEPTING_TRAFFIC` when the instance can serve again. Never use liveness to control maintenance, as that can cause unnecessary restarts.

## 7. Securing Health Endpoints

Kubelet probes need to reach the endpoints, yet detailed diagnostic endpoints should not be exposed indiscriminately. When the application uses Spring Security, permit access only to the exact probe paths in your existing security chain, such as `/livez` and `/readyz`, while keeping other Actuator endpoints behind authentication policy. If using `/actuator/health/...` paths, permit only the specific group endpoints kubelet needs.

Key principles:

- Only expose `health` and truly necessary management endpoints.
- Never expose `env`, `configprops`, `heapdump`, or all Actuator endpoints to public networks.
- Use `show-details: when-authorized` or `never` in production.
- Never include connection strings, credentials, tokens, sensitive hostnames, or exception messages containing user data in health details.
- Restrict network access to management endpoints via network policies, firewalls, or management networks.
- Verify probes can reach endpoints after enabling Spring Security; otherwise, Kubernetes may receive 401/403 and mark Pods failed.

If management endpoints run on a separate port, evaluate whether kubelet can reach that port and whether probes actually verify the main web server. Configuring additional paths on the application port usually avoids the scenario where the management server stays healthy while the request-serving server has failed.

## 8. Manual Testing and Automated Tests

Start the application with Actuator and call the endpoints:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
```

When the application is healthy, endpoints return status `UP` and HTTP 200. When readiness switches to `REFUSING_TRAFFIC`, the readiness endpoint returns an unready status; `DOWN` or `OUT_OF_SERVICE` statuses map to HTTP 503 by default. Liveness should still return `UP` if the process can make progress and only an external dependency is having issues.

You can test readiness transitions in tests or a maintenance workflow by publishing an availability event:

```java
AvailabilityChangeEvent.publish(
    applicationContext,
    ReadinessState.REFUSING_TRAFFIC
);
```

After the state changes, call `/readyz` to verify the HTTP status and response body. Publish `ReadinessState.ACCEPTING_TRAFFIC` to bring the application back to accepting traffic. Never use this operation to simulate a liveness failure in a live user-facing environment.

An integration test can verify the endpoints on a random port:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "management.endpoint.health.probes.enabled=true",
        "management.endpoint.health.probes.add-additional-paths=true"
    }
)
class HealthProbeTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void livenessEndpointIsAvailable() {
        ResponseEntity<String> response = http.getForEntity("/livez", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void readinessEndpointIsAvailable() {
        ResponseEntity<String> response = http.getForEntity("/readyz", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
    }
}
```

This is an example testing the healthy state; your test project needs matching imports, static assertions, and test dependencies. Add tests for custom health indicators covering successful dependency responses, timeouts, and connection errors. If the readiness group includes a database, use a test database or Testcontainers to test dependency states as well. Avoid letting integration tests send health checks to production systems.

## 9. Connecting Health with Metrics, Logs, and Traces

Health endpoints report status at the moment of the check. Observability signals help explain how that status changed and where the root cause lies.

**Metrics.** Track probe failure rate, restart counts, unready Pod counts, startup time, and drain time. Kubernetes metrics usually come from kubelet, kube-state-metrics, or the container platform. On the application side, monitor request latency and dependency-related meters. When computing SLIs for user traffic, consider separating probe requests from business requests so periodic checks do not skew user request rates or latency.

**Logs.** When readiness changes state, logs should record actionable causes: which dependency became unavailable, how long it timed out, which state was published, and which instance was affected. Do not log repeated ERROR stack traces on every kubelet probe if the failure is already logged elsewhere. Avoid logging secrets or sensitive health details.

**Traces.** If probes are instrumented like ordinary HTTP requests, they may show up in `http.server.requests` and the tracing backend. Filter or identify `/livez` and `/readyz` routes when building dashboards and sampling policies. Do not create child spans or make extra service calls from health indicators solely to generate traces; checks must remain lightweight and bounded.

When investigating a Pod that repeatedly loses readiness, correlate probe failure timestamps with deployments, application logs, connection pools, database latency, DNS/network errors, and business request traces. If liveness stays healthy while readiness fails, the process is likely still running but unable to serve; if both liveness and readiness fail, determine whether the fault lies in the process, web server, or probe configuration.

## 10. Practice Scenario: Database Connection Loss

Suppose a Spring Boot service has three replicas. The database becomes temporarily unreachable for two minutes. You configured:

- Liveness includes only `livenessState`.
- Readiness includes `readinessState,db`.
- Kubernetes liveness calls `/livez`; readiness calls `/readyz`.

When the database loses connectivity, the `db` health contributor reports `DOWN`. The readiness group transitions to unready, and Kubernetes stops routing new traffic to the affected Pods. Liveness remains `UP`, so kubelet does not restart all containers merely because of a temporary database disruption.

When the database recovers and the health contributor returns `UP`, the readiness group can return to `UP`; Kubernetes adds the Pods back to Service endpoints. Meanwhile, operations teams inspect connection logs, pool exhaustion metrics, database latency, and alerts from the metrics backend.

If the application has a cache and can still serve part of its requests when the database is disconnected, readiness configuration probably should not include `db`. Instead, readiness reflects actual serving capability, while health details and metrics still provide visibility into the failing database. This decision must be grounded in the API contract and designed degraded-mode behavior, not merely the presence of a datasource in the application.

## 11. Common Issues and Troubleshooting

| Symptom | Common Causes | Resolution |
|---|---|---|
| Kubernetes reports probe 404 | Probes not enabled, additional paths not enabled, or wrong context path | Check Actuator config and curl the endpoint from inside the Pod |
| Probe receives 401/403 | Spring Security blocks kubelet | Permit the exact probe paths in the security chain and restrict network access |
| Management health UP but app accepts no requests | Management server runs on separate port and probes do not check app port | Use additional paths on main port or probe the application port directly |
| All Pods restart when database fails | Database was included in the liveness group | Keep only application liveness state; move dependency checks to readiness if appropriate |
| Pod stays unready even though API can serve | Readiness includes optional dependency or indicator is too sensitive | Align readiness with actual serving capability and review timeouts |
| Pod becomes unready too early on startup | Missing startup probe or readiness ignores incomplete warm-up | Add a startup probe and manage readiness during warm-up |
| Probe timeouts add load | Health indicator calls slow API or runs heavy query | Set short timeouts, reduce work in indicator, and avoid sequential dependency calls |
| Rollout drops in-flight requests | Shutdown not graceful or drain window too short | Enable graceful shutdown and align termination grace period with processing timeouts |
| Dashboard request rate rises due to probes | Probes counted as regular HTTP requests | Identify probe routes and exclude them from business SLIs when appropriate |

## 12. Deployment Checklist

- Spring Boot Actuator is added and required health endpoints are exposed.
- `management.endpoint.health.probes.enabled` is enabled.
- `/livez` and `/readyz` are configured on the application port if the platform checks the main port.
- Liveness reflects process health only, with no external service dependencies.
- Readiness reflects request-serving capability and includes only truly mandatory dependencies.
- Custom health indicators enforce timeouts, handle errors, and return no sensitive data.
- Startup probe fits actual startup duration.
- Security allows kubelet to call probe endpoints while still protecting detailed Actuator endpoints.
- Graceful shutdown and drain times are aligned with Kubernetes.
- Metrics, logs, and traces can distinguish probes from business requests.
- Tested UP, DOWN, readiness refusal, slow startup, and dependency timeout states.

When liveness, readiness, and startup are configured according to their proper roles, the platform can restart stuck processes, stop routing traffic to unready instances, and allow sufficient time for applications to boot. Combining health endpoints with metrics, logs, and traces gives operations teams visibility into both current status and why that status changed.

# Kubernetes Probes in Spring Boot

A Kubernetes probe is the mechanism by which kubelet checks container status to decide when an application has started, whether it needs restarting, or whether it can receive traffic. With Spring Boot, probes usually call Actuator health groups. Misconfiguration can trigger restart loops, place un-warmed pods into service endpoints, or leave broken instances in traffic for too long. Therefore, you must choose the right probe type, endpoint, and time thresholds matching the application's actual lifecycle.

In the **SPRING_BOOT_OBSERVABILITY** module, Kubernetes probes belong to the **Health and readiness** chapter, connecting Actuator health, startup state, liveness/readiness, metrics, logs, and tracing. This lesson focuses on how to design `startupProbe`, `livenessProbe`, and `readinessProbe` for Spring Boot; choosing HTTP/TCP/exec/gRPC probes; configuring Actuator paths/ports/security; calculating timeouts and failure thresholds; coordinating rollouts, draining, testing, and troubleshooting.

## Learning objectives

1. Distinguish `startupProbe`, `livenessProbe`, and `readinessProbe`.
2. Choose an appropriate probe mechanism for Spring Boot.
3. Configure Actuator health groups and Kubernetes manifests.
4. Calculate period, timeout, failure threshold, and startup budget.
5. Avoid restart storms when external dependencies experience outages.
6. Handle separate management ports, security, and network policies.
7. Coordinate readiness with rolling updates and graceful shutdown.
8. Test probe behavior and investigate pod states.

## 1. What is a Kubernetes probe?

Kubelet runs probes periodically against a container. Probe results affect container status and whether the pod is added to endpoints serving traffic.

| Probe | Question | On failure |
| --- | --- | --- |
| `startupProbe` | Has the application completed the startup phase? | Beyond failure threshold, container is restarted |
| `livenessProbe` | Is the application still alive and able to continue? | Container is restarted |
| `readinessProbe` | Is the instance ready to receive traffic? | Pod is marked not ready; receives no traffic via Service |

Do not use the three probes interchangeably. The startup probe protects long startup phases; liveness decides restarts; readiness controls traffic.

### 1.1. Relationship between probes

When `startupProbe` is configured, Kubernetes does not execute liveness and readiness probes until the startup probe succeeds. Afterward, liveness/readiness begin according to their own schedules.

~~~mermaid
flowchart TD
    Start["Container starts"] --> Startup["startupProbe"]
    Startup -->|failure within budget| Startup
    Startup -->|success| Active["Normal probe phase"]
    Active --> Live["livenessProbe"]
    Active --> Ready["readinessProbe"]
    Live -->|failure threshold reached| Restart["Restart container"]
    Live -->|success| Running["Container continues"]
    Ready -->|success| Traffic["Pod can receive traffic"]
    Ready -->|failure| NoTraffic["Pod removed from ready endpoints"]
~~~

Readiness failure does not restart the container on its own. Liveness failure triggers restarts. Startup probe failure beyond its budget can also lead to a restart.

### 1.2. Process running does not imply ready

The JVM can be running, the port listening, and the container state Running, yet the Spring context is incomplete, caches are un-warmed, or essential dependencies are unavailable. Probes must reflect the application state needed for the corresponding action, not merely verify process existence.

## 2. Spring Boot Actuator health groups

Add Actuator:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Enable Kubernetes probes for the health endpoint:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Spring Boot provides health groups with common paths:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Verify behavior for your Spring Boot version. If using a custom management base path or separate port, manifests must match the actual path and port.

### 2.1. Liveness group

The liveness group should reflect the process/application's ability to continue running. Avoid adding databases, brokers, or remote APIs to the liveness group if restarting the application cannot fix the dependency failure. A shared database outage can restart all pods simultaneously and heighten reconnect pressure.

### 2.2. Readiness group

The readiness group reflects whether the instance can serve traffic. It can include mandatory dependencies for core use cases, startup readiness state, or custom indicators. Classify optional/fallback dependencies before adding them to the group; a secondary dependency should not stop the entire service from accepting traffic if a degraded mode exists.

### 2.3. Startup state

Spring Boot application availability includes `LivenessState` and `ReadinessState`. During startup, readiness usually stays at `REFUSING_TRAFFIC` until the application is ready. If asynchronous warm-up runs after lifecycle events, the application must keep readiness refusing until critical warm-up finishes.

Kubernetes `startupProbe` gives the process extra time to start; it does not automatically know business warm-up finished unless the startup endpoint reflects that state.

## 3. Types of probe mechanisms

Kubernetes supports multiple check mechanisms:

| Mechanism | How it works | Suitable when |
| --- | --- | --- |
| HTTP GET | Sends an HTTP request and evaluates status code | Spring Boot Actuator health endpoints |
| TCP Socket | Checks whether the port accepts connections | Only need to verify open socket |
| Exec | Runs a command inside the container | Specialized local checks needed |
| gRPC | Calls the gRPC health checking protocol | Application exposes a gRPC health service |

### 3.1. HTTP GET

This is typically the right choice for Spring Boot because Actuator returns health statuses with clear semantics. HTTP probes inspect the response code; 200–399 is treated as success, other responses as failure. Ensure DOWN/OUT_OF_SERVICE maps to an appropriate failure status code.

### 3.2. TCP socket

A TCP probe only proves the port accepts connections. It does not prove the Spring context is ready, the database is working, or request handlers can serve. A TCP probe may suit preliminary startup or services without an HTTP health endpoint, but is too shallow to replace application readiness semantics.

### 3.3. Exec probe

An exec probe runs a command inside the container. Commands can check files/sockets/local processes, yet spawn extra processes and can consume resources if run frequently. Avoid heavy shell scripts or commands relying on tools missing from minimal container images.

### 3.4. gRPC probe

If the application provides the gRPC health checking protocol, Kubernetes can use a `grpc` probe. Ensure the health service reflects the intended readiness/liveness semantics. Actuator HTTP endpoints do not automatically expose the gRPC health protocol.

## 4. Configuring probes in a Deployment

Example Deployment for Spring Boot running on HTTP port 8080:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
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
            failureThreshold: 2
~~~

This is an illustrative configuration. The startup probe grants up to roughly 150 seconds per the example's period/failure threshold, though exact timing also depends on scheduling and probe execution. Choose parameters based on measured startup duration and rollout budget.

### 4.1. initialDelaySeconds and startupProbe

When `startupProbe` is present, you generally do not need a long `initialDelaySeconds` on liveness/readiness to cover slow startups; `startupProbe` already protects that phase. You can use `initialDelaySeconds` when an explicit extra delay is required, but avoid confusing overlapping configs.

### 4.2. timeoutSeconds

`timeoutSeconds` is the time limit for a single probe attempt. Health indicators must complete faster than the timeout. If an indicator calls a database or remote API, set client timeouts lower than the total probe timeout so Actuator can return a controlled result.

### 4.3. periodSeconds

`periodSeconds` is the interval between probes. Polling too frequently can generate extra load, especially when each probe calls multiple external dependencies. Polling too infrequently slows failure detection. Balance against your failure detection budget and health check cost.

### 4.4. failureThreshold and successThreshold

`failureThreshold` is the number of consecutive failures before a probe is considered failed. `successThreshold` specifies consecutive successes required to transition back to success; readiness probes can use it to reduce flapping, whereas startup/liveness follow specific Kubernetes semantics. Check Kubernetes version and probe type when configuring.

## 5. Calculating startup budget and failure detection

Startup budget must cover normal startup time plus required warm-up and reasonable variance. With a startup probe of `periodSeconds = 5` and `failureThreshold = 30`, the nominal budget is roughly 150 seconds.

For example, suppose an application has p99 startup of 35 seconds, p99 cache warm-up of 40 seconds, dependency initialization of 15 seconds, and a safety margin of 30 seconds. An initial startup budget of around 120 seconds is suggested. Re-measure with startup metrics in a production-like environment; never treat this estimate as a fixed configuration.

### 5.1. Failure detection budget

With probe period $P$, timeout $T$, and failure threshold $F$, failure detection time is roughly on the order of $P \times F$, though actual timing depends on the first probe timing, request duration, and scheduling. Do not interpret the simple formula as an exact deadline.

### 5.2. Liveness threshold

Liveness failures lead to restarts. Set thresholds forgiving enough to tolerate brief pauses such as CPU throttling, GC pauses, or transient load. An overly sensitive threshold can trigger a restart loop; an overly loose threshold can leave a deadlocked process running too long.

### 5.3. Readiness threshold

Readiness may need quick recovery so pods return to traffic, yet must avoid flapping when a dependency flickers. Use `successThreshold`, caching/hysteresis inside the application where appropriate, and circuit breakers for business calls.

## 6. Separate management port and networking

Spring Boot can run Actuator on a dedicated management port:

~~~yaml
management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
~~~

In that case, probes must use port 8081 and paths matching the base path/health group. If base path is `/manage`, verify the actual group endpoints are `/manage/health/liveness` and `/manage/health/readiness`.

### 6.1. Management port is not a security boundary

A separate port is not automatically protected. Pod network, `NetworkPolicy`, service mapping, and security chains still govern who can access it. Do not expose the management port through a public Service unless needed.

### 6.2. Management context and application context

When the management server runs on a separate port, it may have its own web server/context. The health endpoint must still be reachable from kubelet. Test from the pod/container perspective and verify the liveness endpoint does not depend on business server routes.

### 6.3. NetworkPolicy

If applying a `NetworkPolicy`, allow kubelet/node probe paths according to the cluster's network model. A policy blocking probes can cause pods to restart or stay not ready even when the application is healthy. Inspect events and network reachability before changing health code.

## 7. Security and health details

Kubernetes probes usually need to read status without component details. Actuator configuration can hide details:

~~~yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
~~~

If a security chain requires authentication on the health endpoint, standard kubelet HTTP probes do not automatically send bearer tokens like a custom HTTP client. You can use a separate port/path/network, permit only the specific health paths in the security chain, or pick a mechanism matching cluster policy. Only permit minimal status endpoints; keep other management endpoints protected.

### 7.1. HTTP status mapping

HTTP probes evaluate status codes. If health status DOWN returns 503, the probe fails as intended. If a custom status mapping always returns 200, kubelet may treat it as success even if the body reports DOWN. Test actual HTTP status codes rather than only reading the JSON body.

### 7.2. Do not let details expose topology

Public health responses must not contain database hostnames, credentials, internal IPs, stack traces, or connection URLs. Use access-controlled logs/metrics for detailed investigation.

## 8. Dependency checks and cascading failures

Readiness may check mandatory dependencies, whereas liveness should not depend on external systems if restarting cannot fix the outage.

| Dependency | Liveness | Readiness |
| --- | --- | --- |
| JVM/process state | Yes | Indirectly possible |
| Critical database | No | Possible, if all primary requests need it |
| Optional search service | No | Usually no if a fallback exists |
| Analytics broker | No | Usually no if processed async |
| Payment provider | No | Evaluate by traffic/use case |
| Cache with fallback | No | Usually no |

If a shared database fails and readiness turns false on all pods, the service may have zero endpoints left. That may be right if core requests cannot be served, yet degraded modes, fallbacks, and remaining traffic handling must be evaluated.

### 8.1. Do not probe with heavy queries

Health checks should be lightweight and timed out. Avoid full scans, large table counts, or business transactions. High probe frequencies multiply check costs across all pods.

### 8.2. Circuit breakers and probes are different

Circuit breakers govern business calls based on failures/slow calls. Probes report instance state to the orchestrator. Do not use probes in place of circuit breakers or retry policies. Combine timeouts, bulkheads, fallbacks, and readiness policies.

## 9. Rolling updates and readiness

During a rolling update, Kubernetes creates new pods, waits for pods to meet Ready conditions, and then continues the rollout per strategy. Readiness probes decide when a pod can join Service endpoints. If readiness passes too easily, traffic can reach un-warmed instances; if it is too strict, rollouts can stall.

### 9.1. minReadySeconds and rollout strategy

`minReadySeconds` lets a Deployment wait for a pod to remain Ready for a period before considering it available for rollout progress. It does not replace the readiness probe; it adds stability after a pod becomes ready.

`maxUnavailable` and `maxSurge` control how many pods can be unavailable or created ahead during a rollout. Size them based on capacity, startup time, and dependency load tolerance.

### 9.2. Slow startup and rollout timeout

If the startup budget exceeds the Deployment's progress deadline, a rollout may be marked failed before pods become ready. Align `startupProbe` budget, `progressDeadlineSeconds`, rollout strategy, and image pull/scheduling time.

## 10. Graceful shutdown and termination

When a pod is terminated, Kubernetes sends SIGTERM and starts the termination grace period. Spring Boot graceful shutdown can stop accepting new requests and wait for in-flight requests to finish.

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Readiness should transition to `REFUSING_TRAFFIC` when shutdown starts so the pod is drained from routing. Updating endpoints/load balancers takes time. Coordinate termination grace period, `preStop`/drain behavior, and server shutdown timeout.

### 10.1. Do not rely solely on sleep

A fixed `preStop` sleep can provide a buffer, yet does not prove traffic has drained. Design around readiness transitions, load balancer propagation, in-flight request durations, and real grace periods. Never set the grace period shorter than the time valid requests need to finish.

## 11. Testing Kubernetes probes

Testing health code inside the JVM is insufficient to prove kubelet can reach the endpoint in a cluster. Test across multiple layers:

| Test | Verifies |
| --- | --- |
| `HealthIndicator` unit test | Contributor logic and timeouts |
| MockMvc/integration test | Actuator path, status code, security |
| Container smoke test | Port/path inside the runtime image |
| Manifest validation | YAML schema and probe fields |
| Kind/minikube test | Kubelet probe behavior in a test cluster |
| Rollout test | Pods only become Ready after warm-up |
| Termination test | Readiness goes false and graceful drain runs |

### 11.1. Testing endpoint responses

Send requests to the exact path and verify HTTP status, not just the JSON body. Test both anonymous probe callers and authorized callers if policy distinguishes them.

### 11.2. Testing startup delay

Create a warm-up fixture with a controlled delay. Verify `startupProbe` does not fail the container before budget, readiness does not succeed before warm-up completes, and afterward the pod becomes Ready.

### 11.3. Testing liveness failure

In a test environment, simulate an unrecoverable application state per policy. Verify liveness failure leads to a restart. Never intentionally trigger deadlocks or kill production processes just to test probes.

### 11.4. Testing readiness flapping

Simulate a flaky dependency and inspect pod readiness transitions. Assess impact on endpoints, traffic distribution, and rollouts. Verify thresholds/hysteresis curb flapping while still detecting outages within budget.

## 12. Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Pod restart loop | Liveness/startup probe failing | Check pod events, container logs, and probe paths |
| Pod Running yet NotReady | Readiness group DOWN or wrong path | Call endpoint from inside pod and check contributors |
| Probe connection refused | Wrong port or server not listening yet | Verify `containerPort`/management port |
| Probe HTTP 404 | Wrong base path or group path | Check Actuator exposure/path |
| Probe HTTP 401/403 | Security chain blocks kubelet | Permit the right health path or apply matching policy |
| Probe timeout | Indicator blocking or timeout too low | Reduce check cost and set dependency timeouts |
| Startup probe fails after deploy | Startup budget smaller than actual startup | Measure startup duration, raise budget reasonably |
| All pods restart when DB fails | Liveness depends on database | Separate dependency from liveness |
| Rollout stalled | Readiness never met or short progress deadline | Check warm-up and rollout settings |
| Pod ready before cache warm-up | Readiness transitions too early | Hold `REFUSING_TRAFFIC` until completion |
| Probe hits network timeout | `NetworkPolicy`/node routing | Check reachability and policies |
| Health body DOWN yet probe passes | HTTP status mapping returns success | Check actual status code |
| Shutdown drops requests | Insufficient drain/grace period | Align readiness, server timeout, and termination grace |

### 12.1. Investigation workflow for a non-Ready pod

1. Read pod description and events to see probe type/path/response.
2. Inspect container logs around startup and health indicator failures.
3. Exec into the container or use `port-forward` to call the exact Actuator path.
4. Check HTTP status, management port, base path, and security.
5. Inspect readiness group contributors and `ApplicationAvailability` state.
6. Measure warm-up duration and dependency timeouts.
7. Check `NetworkPolicy` and kubelet reachability.
8. Cross-check Deployment rollout strategy and progress deadline.

## 13. Production checklist

| Criterion | Required evidence |
| --- | --- |
| Startup probe has realistic budget | Measured startup p95/p99 and warm-up |
| Liveness only checks ability to continue | Independent of external dependencies |
| Readiness reflects traffic policy | Mandatory/optional dependencies classified |
| Actuator groups accurate | Liveness/readiness paths tested |
| HTTP status mapping accurate | DOWN returns failure response code |
| Port/base path exact | Manifest matches runtime |
| Security suits kubelet | Only minimal health paths permitted |
| Sensible timeout/frequency | No added load or false timeouts |
| Anti-flapping thresholds | Failure/success thresholds justified |
| Coordinated rolling updates | `maxSurge`/`maxUnavailable`/progress deadline |
| Graceful shutdown/drain | Readiness refusing and sufficient grace period |
| Observability history | Probe failures, startup duration, and restart metrics |
| Manifests validated | CI validates YAML/schema and deploy tests |

## 14. Practice: configuring probes for order-service

**Context:** `order-service` runs three replicas on Kubernetes using Spring Boot Actuator. Caches require warm-up before receiving traffic; PostgreSQL may experience brief interruptions. Currently pods restart when the database fails and occasionally receive traffic before caches are ready.

**Tasks:**
1. Enable Actuator health probes.
2. Verify liveness and readiness health paths.
3. Make the liveness group independent of PostgreSQL.
4. Include PostgreSQL in readiness only if core use cases cannot be served when the DB is unavailable.
5. Keep readiness at `REFUSING_TRAFFIC` during warm-up.
6. Configure `startupProbe` with a budget based on startup/warm-up p99.
7. Configure liveness/readiness period, timeout, and thresholds per failure budget.
8. Check separate management port, base path, and security.
9. Test a dependency outage and verify there is no liveness restart storm.
10. Perform a rolling update and verify new pods only accept traffic after becoming ready.
11. Terminate a pod while serving requests; verify graceful shutdown and draining.
12. Write a runbook for restart loops, NotReady, timeouts, and stalled rollouts.

**Expected outcome:** Kubernetes Deployment manifest, Actuator health groups, probe behavior test, rollout/shutdown evidence, and runbook.

## 15. Key takeaways

Kubernetes probes drive three distinct actions: `startupProbe` protects the startup phase, `livenessProbe` decides restarts, and `readinessProbe` decides whether the pod accepts traffic. Spring Boot Actuator provides health groups suited to represent liveness/readiness; paths, ports, security, and HTTP status mappings must match the manifest.

Size the startup budget around measured startup and warm-up durations. Liveness should not depend on databases/brokers if restarting cannot resolve the outage. Readiness must reflect genuinely mandatory dependencies and degraded modes. Align probe timeouts/thresholds with failure budgets, rollout strategies, and graceful shutdown. Test in a Kubernetes environment resembling production; use logs, metrics, and events to investigate probe failures rather than looking only at Running/NotReady states.

**References:**
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Kubernetes — Configure Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Kubernetes — Deployments and Rolling Updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)

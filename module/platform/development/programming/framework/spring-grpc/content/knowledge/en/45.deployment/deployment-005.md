# Health Checks for Orchestrators

## 1. Objectives

When deploying Spring gRPC on Kubernetes or another orchestrator, the platform needs to know when the process has started, when an instance can receive traffic, and when the process is no longer functioning normally. An open TCP port does not answer those questions. For gRPC, the appropriate signal is a health service following the standard gRPC Health Checking protocol, wired to the application's lifecycle and readiness state.

**Health checks for orchestrators** are how the deployment platform actively inspects service state and takes appropriate action. Kubernetes supports startup, liveness, and readiness probes; for gRPC, a native gRPC probe calls the `Health/Check` method of the standard `grpc.health.v1` service.

After this lesson, you can:

- Distinguish startup, liveness, and readiness probes.
- Implement the gRPC Health Checking service for a Spring gRPC server.
- Configure Kubernetes gRPC probes with appropriate service names.
- Synchronize health status with startup, dependency readiness, and shutdown.
- Choose between native gRPC probes and exec probes when TLS/auth is required.
- Tune timeouts, periods, and failure thresholds to avoid restart storms.
- Test probes from the orchestrator's perspective.

## 2. Three Probe Types Have Three Different Roles

Kubernetes uses three probe types to control container lifecycles:

| Probe | Question | When probe fails |
|---|---|---|
| Startup | Has the application finished its startup phase? | Container is restarted after exceeding failure threshold |
| Liveness | Is the process alive and able to keep running? | Kubelet restarts the container |
| Readiness | Is the instance eligible to receive traffic? | Pod is marked not ready and removed from traffic-serving endpoints |

Startup probes protect slow-starting applications. While the startup probe has not succeeded, Kubernetes does not run liveness or readiness probes. Once the startup probe succeeds, the other two probes begin running per configuration.

Liveness detects wedged processes or unrecoverable internal states. Do not include every dependency in liveness. If a database temporarily loses connectivity and liveness fails as well, the orchestrator may restart all instances simultaneously, making it even harder for an overloaded database to recover.

Readiness answers whether the instance should receive new requests. It can depend on a database or mandatory dependencies. When readiness fails, Kubernetes stops routing new traffic to the pod; the container keeps running so it can recover.

## 3. gRPC Health Checking Protocol

gRPC defines a standard service in the `grpc.health.v1` package:

- `Health/Check` is a unary RPC returning the service's current status.
- `Health/Watch` is a server-streaming RPC sending the current status and subsequent changes.

Kubernetes native gRPC probes call `Health/Check`. They do not use `Watch`.

The request includes the service name to check. Conventions:

- An empty service name `""` represents the overall status of the server.
- A specific service name, such as `catalog.v1.CatalogService`, represents a single gRPC service.

The service name must match the Protobuf package and service name, not necessarily the Java package. If Kubernetes queries a service name unknown to the health server, the probe will fail.

Standard statuses:

| Status | Meaning |
|---|---|
| `UNKNOWN` | Status undetermined |
| `SERVING` | Service is ready to serve |
| `NOT_SERVING` | Service is not ready or is shutting down |
| `SERVICE_UNKNOWN` | Service name is unmanaged; typically appears in `Watch` |

For `Check`, an unregistered service typically returns gRPC status `NOT_FOUND`. The orchestrator should only consider a probe successful when it receives a valid health response with status `SERVING`.

## 4. Providing the Health Service in Spring gRPC

gRPC Java provides `HealthStatusManager` in the `grpc-services` artifact. The manager holds status per service name and provides the standard health service implementation.

The dependency should use the same release line as the rest of the gRPC Java artifacts:

```kotlin
dependencies {
    implementation("io.grpc:grpc-services:<grpc-version>")
}
```

Example bean creation:

```java
@Configuration
public class GrpcHealthConfiguration {

    @Bean
    HealthStatusManager healthStatusManager() {
        return new HealthStatusManager();
    }

    @Bean
    BindableService grpcHealthService(
            HealthStatusManager manager) {
        return manager.getHealthService();
    }
}
```

A `BindableService` bean is only auto-registered if the Spring gRPC starter/version in use supports discovering that bean type. If the starter uses a dedicated server factory, service registry, or customizer, register `manager.getHealthService()` through the starter's proper mechanism. Verify that the health service is bound to the exact gRPC listener that Kubernetes probes call.

For a manually constructed server, register it directly:

```java
Server server = ServerBuilder.forPort(9090)
        .addService(catalogService)
        .addService(manager.getHealthService())
        .build()
        .start();
```

Do not create `HealthStatusManager` and forget to register the health service. In that case, the port is open, yet Kubernetes probes calling `grpc.health.v1.Health/Check` will receive `UNIMPLEMENTED`.

## 5. Managing Separate Service Names per Probe

Different service names can represent readiness and liveness:

- `liveness`: the process and gRPC server can still respond to health calls.
- `readiness`: the instance is ready to accept business traffic.
- `catalog.v1.CatalogService`: serving status of the Catalog service.
- `""`: overall status if the application defines it clearly.

When using separate service names, update all corresponding statuses in `HealthStatusManager`. The Kubernetes probe sends the exact string configured in the `service` field; case or package mismatches will cause the probe to fail.

Example coordinator:

```java
public final class GrpcProbeStatus {

    private static final String LIVENESS = "liveness";
    private static final String READINESS = "readiness";
    private static final String CATALOG =
            "catalog.v1.CatalogService";

    private final HealthStatusManager manager;

    public GrpcProbeStatus(HealthStatusManager manager) {
        this.manager = manager;
    }

    public void starting() {
        setAll(ServingStatus.NOT_SERVING);
    }

    public void processAlive() {
        manager.setStatus(LIVENESS, ServingStatus.SERVING);
    }

    public void ready() {
        manager.setStatus(READINESS, ServingStatus.SERVING);
        manager.setStatus(CATALOG, ServingStatus.SERVING);
    }

    public void notReady() {
        manager.setStatus(READINESS, ServingStatus.NOT_SERVING);
        manager.setStatus(CATALOG, ServingStatus.NOT_SERVING);
    }

    public void stopping() {
        setAll(ServingStatus.NOT_SERVING);
    }

    private void setAll(ServingStatus status) {
        manager.setStatus(LIVENESS, status);
        manager.setStatus(READINESS, status);
        manager.setStatus(CATALOG, status);
        manager.setStatus("", status);
    }
}
```

The example above illustrates the statuses to publish. In a real implementation, do not set liveness to `NOT_SERVING` just because the database is unavailable; separate liveness transitions from readiness according to the true semantics of the two probes. Once startup finishes, liveness can be `SERVING` even while readiness remains `NOT_SERVING` because a mandatory dependency has not connected yet.

## 6. Synchronizing Status with the Spring Lifecycle

A common deployment sequence:

1. Create `HealthStatusManager` with initial service statuses set to `NOT_SERVING`.
2. Initialize Spring beans, configure the server, and initialize service implementations.
3. Wait for mandatory dependencies to complete bounded-timeout readiness checks.
4. Once the process is operational, set liveness to `SERVING`.
5. Once eligible for traffic, set readiness and service statuses to `SERVING`.
6. When graceful shutdown begins, set readiness and service statuses to `NOT_SERVING` before stopping traffic acceptance.
7. Drain in-flight RPCs before stopping the server.

`ApplicationReadyEvent` can be used if the readiness gate has completed by the time the event fires. If dependency readiness continues to change after startup, use a coordinator that tracks dependencies and updates status on state changes. For shutdown, use `SmartLifecycle` or a context shutdown hook matching the starter's ordering.

Do not set readiness to `SERVING` as soon as the port binds. The listener can open before the database, cache, or service handlers are ready.

## 7. Configuring Kubernetes Native gRPC Probes

Kubernetes supports gRPC probes directly in the Pod spec. Example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-grpc
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-grpc
  template:
    metadata:
      labels:
        app: catalog-grpc
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: catalog
          image: example/catalog-grpc:1.0.0
          ports:
            - name: grpc
              containerPort: 9090
              protocol: TCP
          startupProbe:
            grpc:
              port: 9090
              service: liveness
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            grpc:
              port: 9090
              service: liveness
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            grpc:
              port: 9090
              service: readiness
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 1
```

In the example, startup and liveness query service name `liveness`; readiness queries `readiness`. The application must publish those exact two statuses. The startup probe grants the application up to roughly 150 seconds to start based on the period/failure threshold above; actual time also depends on timeouts and probe scheduling.

Native gRPC probes have been stable since Kubernetes 1.27. On older clusters, check the version and feature gates before using them; an exec probe or another check method may be required.

Key fields:

| Field | Meaning |
|---|---|
| `port` | Numeric port of the gRPC listener inside the Pod |
| `service` | Service name sent in `HealthCheckRequest`; can be omitted to query overall status |
| `periodSeconds` | Probe interval |
| `timeoutSeconds` | Maximum time to wait for a probe |
| `failureThreshold` | Consecutive failures before considering the probe failed |
| `successThreshold` | Consecutive successes to recover; must be 1 for liveness/startup |
| `initialDelaySeconds` | Wait time before the first probe, if needed |

## 8. Limitations of Native gRPC Probes

Native gRPC probes have several limitations to account for:

- Only numeric ports are supported, not named ports.
- Cannot configure TLS certificates, client certificates, or authentication metadata.
- Cannot configure an arbitrary hostname like HTTP probes; probes target the Pod IP.
- Cannot supply custom headers or tokens.
- Only call `Health/Check`; do not perform `Health/Watch`.

Thus, native probes fit when the health service can be called over plaintext gRPC within the Pod network and does not require authentication on the probe endpoint. If the application only serves TLS/mTLS or requires a token on every RPC, native probes lack fields to supply those credentials.

Do not disable TLS or authentication for the entire gRPC listener solely to make native probes work. You can design a dedicated health listener/health access policy within the Pod trust boundary, or use an exec probe with a TLS/auth-capable tool.

## 9. When to Use an Exec Probe

An exec probe runs a program inside the container. This is the choice when you need to pass certificates, tokens, or parameters not supported by native gRPC probes.

Example using the `grpc_health_probe` tool:

```yaml
readinessProbe:
  exec:
    command:
      - /bin/grpc_health_probe
      - -addr=127.0.0.1:9090
      - -service=readiness
      - -connect-timeout=1s
      - -rpc-timeout=2s
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 2
```

Binary names and flags depend on the `grpc-health-probe` version packaged in the image. With TLS/mTLS, use the exact CA, certificate, and key options supported by that tool version; manage secrets safely and do not log credentials.

Exec probes incur process creation overhead on each run, so set a reasonable period and keep the binary small. Do not run complex scripts that synchronously call many dependencies on every probe.

Another option is the Spring Boot Actuator HTTP readiness endpoint, though that is a separate HTTP signal. If used, ensure the readiness policy stays consistent with the gRPC health status and do not confuse the HTTP management port with the gRPC listener.

## 10. Designing Liveness to Avoid Restart Storms

Liveness should check whether the process can keep running, not every remote dependency. For example:

- The Spring application context has finished starting up.
- The health handler can respond within a bounded time.
- Essential workers/event loops are not deadlocked according to internal criteria.

Do not include the database, Kafka, Redis, or an optional gRPC downstream in liveness. If a shared dependency suffers an outage, all pods could fail liveness simultaneously and restart continuously.

Readiness may check mandatory dependencies. However, the health coordinator should monitor dependencies with timeouts, cached results, and concurrency limits. Do not let each probe trigger a heavy query or a chain of dependent RPCs.

When a dependency flaps, failure/recovery thresholds or hysteresis can prevent constant status oscillation. However, do not delay marking `NOT_SERVING` if real requests can no longer be processed safely.

## 11. Tuning Timeouts and Thresholds

Overly sensitive probes can cause unnecessary restarts or pod removals. Overly slow probes can leave traffic flowing to a failing instance longer.

Example startup budget calculation:

```text
periodSeconds × failureThreshold
5 seconds × 30 attempts ≈ 150 seconds
```

This is an approximate periodic probe window, not an exact deadline; timeouts and execution scheduling also affect it.

Several guidelines:

- `timeoutSeconds` must exceed normal health handler latency while remaining bounded.
- `periodSeconds` should balance detection speed against probe overhead.
- Readiness `failureThreshold` can be lower than liveness to remove failing instances from traffic earlier.
- Startup `failureThreshold` must accommodate valid slow startups.
- Liveness should not react to a brief latency spike.
- Readiness recovers after `successThreshold` consecutive successes.

Kubernetes native gRPC probes use `timeoutSeconds` as the probe timeout. Verify kubelet behavior for the cluster version in use and do not set timeouts below scheduler/runtime capabilities under high load.

## 12. Shutdown and Readiness Propagation

When a pod is terminated, notify the orchestrator to stop sending new requests before the process closes its listener:

1. Receive the shutdown signal.
2. Set readiness and service statuses to `NOT_SERVING`.
3. Wait for `EndpointSlice`/load balancers to update and stop selecting the pod.
4. Send `GOAWAY`/drain connections if supported by the server/proxy.
5. Let in-flight RPCs finish within the grace period.
6. Cancel remaining calls when time expires.
7. Close the server and process.

`terminationGracePeriodSeconds` must be long enough for propagation and draining without violating rollout policies. A `preStop` hook can assist with a wait window if the architecture requires it, but does not replace updating the readiness status.

If status is only changed after the server has stopped, probes cannot observe `NOT_SERVING` and load balancers may continue sending traffic to a departing endpoint.

## 13. Testing and Diagnostics

### Calling the Health RPC Directly

You can use `grpcurl` if the endpoint permits an appropriate connection:

```bash
grpcurl -plaintext \
  -d '{"service":"readiness"}' \
  localhost:9090 \
  grpc.health.v1.Health/Check
```

The result should show status `SERVING` when the pod is ready. If the server uses TLS, omit `plaintext` and configure CA/client certificates matching the endpoint.

### Testing from Inside the Pod

Run the same tool or exec probe inside the corresponding container/network namespace to verify:

- The listener is on the right port.
- The health service is registered.
- Service names match.
- Status transitions follow startup/readiness/shutdown.
- The probe timeout is sufficient for the health handler.

### Inspecting Kubernetes Events

Use `kubectl describe pod` and inspect events/logs to distinguish:

- `Connection refused`: listener not bound or wrong port.
- `Deadline exceeded`/timeout: slow health handler, busy workers, or broken network path.
- `UNIMPLEMENTED`: health service not registered.
- `NOT_FOUND`: probe service name does not exist.
- `NOT_SERVING`: application actively reporting unready.
- TLS/auth errors with exec probe: incorrect trust, certificate, or credentials.

Do not treat every probe failure by increasing timeouts. First determine whether the issue is startup, service registration, wrong service name, dependency readiness, or transport/security.

## 14. Testing

### Unit Testing the Status Coordinator

Verify transitions:

- Startup: readiness `NOT_SERVING`.
- Process startup complete: liveness `SERVING`.
- Mandatory dependency ready: readiness `SERVING`.
- Mandatory dependency lost with no fallback: readiness `NOT_SERVING`.
- Shutdown initiated: readiness `NOT_SERVING` before server closes.

### In-Process gRPC Health Test

Register `manager.getHealthService()` on a server created with `InProcessServerBuilder`, create a channel with `InProcessChannelBuilder`, and call `Check` using the generated `HealthBlockingStub` with the exact service name. Verify the response status changes after each transition. For `Watch`, verify the initial status and updates using a bounded-timeout latch.

### Kubernetes Integration Test

Deploy a test Pod with native gRPC startup/liveness/readiness probes. Verify:

- An unready pod is not added to Service endpoints.
- Once dependencies are ready, the pod transitions to Ready.
- When readiness returns `NOT_SERVING`, the pod is removed from traffic without restarting the container.
- When liveness fails consecutively, the container is restarted.
- The startup probe protects long startup times.
- During termination, readiness changes before the server closes.

Specifically test native gRPC probes on the actual cluster version. If the server enforces TLS/mTLS, confirm native probes are unsuitable and test an exec probe or a protected internal health endpoint.

## 15. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Port open but gRPC probe fails | Health service not registered | Bind `HealthStatusManager` service to the right server |
| Probe returns `NOT_FOUND` | Service name mismatch | Use exact Protobuf full service name or register the probe name |
| Probe returns `UNIMPLEMENTED` | Server lacks `Health/Check` | Add the gRPC health service |
| Pods restart during database outage | Liveness depends on database | Move dependency checks to readiness |
| Pod Ready before dependencies are ready | Status set to `SERVING` too early | Use a readiness gate |
| Native probe cannot connect to TLS server | Native probe lacks TLS/auth fields | Use an exec probe or design separate health access |
| Probe fails due to named port | gRPC probe requires numeric port | Declare a numeric port |
| Pod removed from traffic yet restarted | Confused readiness with liveness | Only fail readiness when traffic should stop |
| Shutdown drops RPCs | Did not report `NOT_SERVING` and drain early | Update status, propagation, and grace period |
| Probes create heavy load | Each probe triggers a heavy dependency chain | Cache state, set timeouts, and limit concurrency |

## 16. Hands-on Exercise

**Scenario:** Catalog Spring gRPC runs on Kubernetes. The application takes about 90 seconds to start and needs PostgreSQL before handling `GetProduct`. Currently the Deployment only has a TCP liveness probe, so pods occasionally receive traffic before the database is ready.

Perform the following:

1. Register the `grpc.health.v1.Health` service using `HealthStatusManager` on the gRPC server.
2. Initialize the `liveness` and `readiness` service names as `NOT_SERVING`.
3. Configure `startupProbe` to allow up to roughly 120–150 seconds for startup.
4. Configure `livenessProbe` to reflect only that the process/health handler is alive.
5. Configure `readinessProbe` to reflect PostgreSQL readiness and Catalog service readiness.
6. Set readiness to `SERVING` only after the database check succeeds.
7. Set readiness to `NOT_SERVING` as soon as shutdown starts.
8. Test the native gRPC probe on the target Kubernetes version; if TLS/mTLS is mandatory, choose an exec probe with secure credentials.
9. Simulate a database outage and verify pods are removed from traffic without mass restarts.
10. Simulate a hung health handler and verify liveness restarts per the failure threshold.

**Completion criteria:** startup, liveness, and readiness have distinct semantics; the health service is registered and uses exact service names; probe timeouts/thresholds are reasonable; dependency outages do not trigger restart storms; shutdown updates readiness before closing the listener; tests demonstrate behavior from Kubernetes' perspective.

## 17. Key Takeaways

Orchestrators need a health signal reflecting serving capability, not just a TCP port. Kubernetes startup probes protect slow startups, liveness detects processes that cannot continue, and readiness controls traffic. Native gRPC probes call `grpc.health.v1` `Health/Check`; the application must register the health service and publish exact service names/statuses via `HealthStatusManager`. Keep readiness `NOT_SERVING` during startup and shutdown, switching to `SERVING` only after the readiness gate. Do not put dependency outages into liveness because that can cause restart storms. Native gRPC probes use numeric ports and do not support TLS/auth metadata; if the server enforces TLS/mTLS, consider an exec probe with appropriate tools and credentials. Tune timeouts, periods, failure thresholds, and termination grace periods to the workload. Test status transitions, probe behavior, and endpoint routing on real Kubernetes.

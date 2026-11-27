# Do Not Treat an Open Port as a Healthy Service

## 1. Objectives

An open TCP port only indicates that a process or proxy is listening and the network can establish a TCP-level connection. It does not prove that the Spring gRPC application has finished initializing, that services are registered, that mandatory dependencies are working, or that RPCs can handle business logic properly.

**Service health** must be evaluated by the ability to perform the role the system expects. For gRPC, distinguish three signals:

- **Port/listener availability:** a connection can be established to the address and port.
- **gRPC protocol availability:** a gRPC call can be initiated and registered methods invoked.
- **Application readiness:** the service is ready to accept traffic and required conditions for processing requests are met.

In Spring gRPC, provide the gRPC Health Checking protocol, update status based on lifecycle and dependency readiness, and let load balancers, orchestrators, or clients use that signal. Do not treat an open port or TLS handshake as sole proof that a service is healthy.

After this lesson, you can:

- Explain the limitations of TCP port checks and TLS handshakes.
- Distinguish liveness, readiness, and startup health.
- Implement the gRPC Health Checking protocol with Check and Watch.
- Manage NOT_SERVING and SERVING statuses across the Spring application lifecycle.
- Evaluate dependency health without creating heavy load or restart storms.
- Design health probes and handle health check errors in clients/orchestrators.
- Test service readiness rather than only checking the port.

## 2. What does an open port prove?

When a TCP probe successfully connects to a gRPC port, it only confirms that:

1. The address is routable.
2. A process or proxy is accepting TCP connections.
3. The port is not closed or blocked by a firewall at the time of the probe.

This probe does not know:

- Whether the Spring application context has finished creating.
- Whether generated gRPC services have been registered.
- Whether handlers can process requests or are failing.
- Whether the database, cache, message broker, or mandatory services are available.
- Whether the server returns statuses and responses matching the contract.
- Whether TLS identity and RPC invocation permissions are valid.

For example, a process can bind its port before the database connection finishes. The TCP probe reports success while RPCs requiring the database fail. Similarly, a proxy sidecar can continue accepting TCP connections even if the application process behind it has stopped.

| Signal | What it proves | What it does not prove |
|---|---|---|
| TCP port open | Listener accepts TCP connections | gRPC methods or business logic work |
| TLS handshake succeeds | Both sides completed handshake and certificate check per config | Service is ready to handle requests |
| HTTP/2 connection established | HTTP/2 transport can be established | Specific gRPC methods are registered |
| An arbitrary RPC returns OK | That method successfully handled one specific request | All services and dependencies are healthy |
| gRPC health returns SERVING | Server reports the service is serving | Every future request is guaranteed to succeed |

Health status is an intentional signal published by the application. Its value depends on the application updating status accurately against real readiness conditions.

## 3. Distinguishing liveness, readiness, and startup

Three probe types answer three different questions:

| Probe | Question | What does the system typically do on failure? |
|---|---|---|
| Liveness | Is the process still alive and able to keep running? | Restart the process/container |
| Readiness | Is the instance eligible to receive traffic? | Temporarily stop routing traffic to the instance |
| Startup | Has the application completed its startup phase? | Keep waiting for startup or restart when threshold is exceeded |

Do not put every dependency into liveness. If the database temporarily loses connectivity and liveness also fails, the orchestrator may restart all instances continuously, worsening the outage.

Readiness can depend on a database or dependency if requests cannot be processed properly without it. However, include only mandatory dependencies in readiness. An optional dependency should have a degraded mode or fallback if business rules permit.

Startup probes are helpful when a Spring application needs time to load configuration, migrate data, warm caches, or register services. During this phase, the instance should not be considered dead just because it is not ready yet.

## 4. The gRPC Health Checking protocol

gRPC defines a standard health service in the grpc.health.v1 package:

- Health/Check: unary RPC returning the current status of a service.
- Health/Watch: server-streaming RPC sending the current status and subsequent changes.

The request contains a service name. Common conventions:

- The empty string represents the overall health of the server.
- A full name such as catalog.v1.CatalogService represents a specific service.

The service name must match the Protobuf package and service name used to construct the full method path. Do not use the Java package if it differs from the Protobuf package.

Health responses have these statuses:

| Status | Meaning |
|---|---|
| UNKNOWN | Status has not yet been determined |
| SERVING | Service is ready to serve |
| NOT_SERVING | Service is currently not ready |
| SERVICE_UNKNOWN | The queried service is unknown to the health server; typically appears in Watch |

With Check, an unknown service is typically represented by gRPC status NOT_FOUND. With Watch, the server can send SERVICE_UNKNOWN so the client knows the service name is not managed. Clients must also distinguish transport errors or UNIMPLEMENTED when the server does not implement the health service.

Check is appropriate for periodic probes. Watch is appropriate for clients or control planes wanting continuous updates without constant polling.

## 5. Registering the health service in the gRPC server

gRPC Java provides HealthStatusManager in the grpc-services artifact. This component manages statuses and supplies the standard health service implementation.

The dependency must match the release line of the gRPC Java libraries in use:

```kotlin
dependencies {
    implementation("io.grpc:grpc-services:<grpc-version>")
}
```

Replace grpc-version with the version centrally managed in your project's BOM or dependency constraints.

Example manager configuration:

```java
import io.grpc.BindableService;
import io.grpc.protobuf.services.HealthStatusManager;

@Configuration
public class GrpcHealthConfiguration {

    @Bean
    HealthStatusManager healthStatusManager() {
        return new HealthStatusManager();
    }

    @Bean
    BindableService grpcHealthService(
            HealthStatusManager healthStatusManager) {
        return healthStatusManager.getHealthService();
    }
}
```

A BindableService bean is auto-registered only if your project's Spring gRPC starter/version supports discovering that bean type. If the starter requires registering services via a dedicated registry or server factory, register healthStatusManager.getHealthService() through that mechanism. What matters is that the health service is bound to the exact gRPC server/port that probes call.

If the server is built manually, you can register it directly:

```java
Server server = ServerBuilder.forPort(port)
        .addService(catalogService)
        .addService(healthStatusManager.getHealthService())
        .build()
        .start();
```

Do not open a separate health port solely to make probes turn green while the business gRPC server is not yet ready, unless the architecture intentionally separates control plane and data plane. If separating ports, clearly document which part of the system that signal proves.

## 6. Updating status with the Spring lifecycle

Do not set a service to SERVING immediately upon creating HealthStatusManager. When the application first starts, dependencies or service handlers may not be ready yet.

A typical sequence:

1. Initialize the manager with overall status NOT_SERVING.
2. Set each service status to NOT_SERVING.
3. Initialize configuration, service beans, and mandatory dependencies.
4. Check readiness conditions with a deadline.
5. Only when ready, update service and overall status to SERVING.
6. When graceful shutdown begins, transition status back to NOT_SERVING before stopping traffic acceptance.

Example status updates:

```java
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;

public final class CatalogReadiness {

    private static final String CATALOG_SERVICE =
            "catalog.v1.CatalogService";

    private final HealthStatusManager health;

    public CatalogReadiness(HealthStatusManager health) {
        this.health = health;
    }

    public void markStarting() {
        health.setStatus("", ServingStatus.NOT_SERVING);
        health.setStatus(
                CATALOG_SERVICE, ServingStatus.NOT_SERVING);
    }

    public void markReady() {
        health.setStatus(
                CATALOG_SERVICE, ServingStatus.SERVING);
        health.setStatus("", ServingStatus.SERVING);
    }

    public void markStopping() {
        health.setStatus(
                CATALOG_SERVICE, ServingStatus.NOT_SERVING);
        health.setStatus("", ServingStatus.NOT_SERVING);
    }
}
```

HealthStatusManager.setStatus() updates the status published by the health service, including to clients watching via Watch. In a real application, invoke these methods from a lifecycle coordinator with clear ordering. You can use ApplicationReadyEvent after the readiness gate completes and ContextClosedEvent or SmartLifecycle.stop() to report NOT_SERVING before the server stops. The hook chosen must match the starter's startup and shutdown order.

If a server hosts multiple services, do not set all of them to SERVING just because one service is ready. Update status individually for each full service name and compute overall status per published policy.

## 7. Readiness must reflect actual serving capability

A healthy service does not necessarily have every dependency in perfect shape. Readiness must reflect the dependencies required for the requests the instance receives.

Catalog example:

| Component | Role | Readiness impact |
|---|---|---|
| Catalog database | Core product reads/writes | Typically mandatory |
| Cache | Speeds up queries | Can be degraded if the database can still handle load |
| Search index | Supports advanced search | Depends on endpoint and fallback |
| Metrics exporter | Exports telemetry | Usually does not cause business readiness loss |
| Recommendation service | Related suggestions | Can be optional |

If the database is mandatory, losing connectivity can transition Catalog to NOT_SERVING. If the cache goes down while the system can query the database directly within load limits, the service can stay SERVING while emitting degraded metrics.

For a service with many methods, a dependency may affect only part of the API. The standard health service only publishes status by service name, not per RPC method. If one method is unavailable while others still work, consider:

- Splitting services along real availability boundaries.
- Keeping the service SERVING if most of the contract is still fulfilled and handling errors in the specific method.
- Using endpoint-group readiness policies at the routing layer if infrastructure supports it.

Do not mark the entire server NOT_SERVING because an optional feature fails if core capabilities still fulfill the contract.

## 8. Avoiding synchronous dependency calls on every probe

Health probes are called repeatedly by orchestrators, load balancers, and monitoring. If every Check opens database connections, runs heavy queries, and calls every dependency, probes can generate significant load.

Better design:

- Update readiness from lifecycle events and periodically monitored health state.
- Use short, bounded timeouts for dependency health checks.
- Cache results for an appropriate window along with the last-checked timestamp.
- Limit concurrency of dependency probes.
- Use a circuit breaker or state machine if dependencies flap.
- Distinguish degraded from NOT_SERVING by business impact.
- Never allow health probes to wait indefinitely or exhaust worker threads.

Do not use a health RPC to execute complex synthetic transactions or write production data every few seconds. If synthetic monitoring is needed, separate it from readiness probes and cap its frequency.

## 9. Liveness is not dependency readiness

Liveness answers whether the process can keep running. It should focus on unrecoverable internal failures, such as deadlocks or a stuck runtime by measurable criteria.

Readiness answers whether the instance should receive traffic. It can reflect the database or mandatory dependencies.

| Incident | Liveness | Readiness |
|---|---|---|
| Database temporarily disconnected | Usually stays healthy | May become NOT_SERVING if DB is mandatory |
| Cache lost but fallback exists | Healthy | May stay SERVING, record degraded metric |
| Spring context has not finished startup | Process is alive | NOT_SERVING |
| Event loop/worker pool severely deadlocked | May fail per policy | Typically not ready |
| Graceful shutdown in progress | Process stays alive during drain phase | NOT_SERVING |

If liveness depends on the database, a database outage can make the orchestrator repeatedly restart every instance. Restarted instances then all reconnect to the database simultaneously, spiking load right as the dependency is recovering.

## 10. Calling Health/Check from a client

The health service has standard generated stubs in gRPC Java. Example client checking Catalog:

```java
HealthGrpc.HealthBlockingStub healthStub =
        HealthGrpc.newBlockingStub(channel)
                .withDeadlineAfter(
                        500, TimeUnit.MILLISECONDS);

HealthCheckResponse response = healthStub.check(
        HealthCheckRequest.newBuilder()
                .setService("catalog.v1.CatalogService")
                .build());

boolean serving =
        response.getStatus() == ServingStatus.SERVING;
```

This snippet requires generated health classes from grpc-services and corresponding imports in io.grpc.health.v1. Health checks also need a deadline; probes must never wait indefinitely.

Distinguish:

- Response SERVING: server reports the service is ready.
- Response NOT_SERVING: server still answers health RPCs but is not accepting business traffic.
- gRPC NOT_FOUND: health server does not know the queried service name.
- gRPC UNIMPLEMENTED: server does not expose the corresponding health method.
- UNAVAILABLE, timeout, or TLS error: health endpoint could not be verified; never interpret as SERVING.

If a health RPC fails due to network/TLS, the probe should report unhealthy or unknown according to orchestrator policy. Never replace that error with a passing result just because the TCP port is still open.

## 11. Using Health/Watch to receive changes

Watch is a server-streaming RPC. The server sends the current status and sends updates whenever the status changes:

```java
HealthGrpc.HealthStub healthStub =
        HealthGrpc.newStub(channel);

healthStub.watch(
        HealthCheckRequest.newBuilder()
                .setService("catalog.v1.CatalogService")
                .build(),
        new StreamObserver<>() {
            @Override
            public void onNext(HealthCheckResponse response) {
                updateLocalReadiness(response.getStatus());
            }

            @Override
            public void onError(Throwable error) {
                markHealthStreamUnknown(error);
            }

            @Override
            public void onCompleted() {
                markHealthStreamClosed();
            }
        });
```

Clients must handle stream closure, transport errors, and reconnects per policy. Do not treat a once-opened stream as eternal proof of health. If a client needs the latest status after reconnecting, create a new watch and receive the current status again.

Watch suits control planes or clients managing multiple backends. For simple periodic probes, Check is usually easier to operate. Do not open a new Watch for every inbound business request.

## 12. Integrating with Spring Boot Actuator

Spring Boot Actuator has health indicators and health endpoints for the HTTP management plane. The gRPC Health Checking protocol is a separate RPC service. The two mechanisms are not automatically synonymous:

- Actuator may report a database indicator UP while the gRPC service is not yet registered.
- gRPC Health may report SERVING even while an optional health indicator is DOWN.
- An open HTTP management port does not prove the gRPC listener is working.

If the application uses Actuator, you can share a readiness coordinator or health state between both endpoints:

1. Dependency-checking components update the internal readiness state.
2. The Actuator readiness group reads that state.
3. The gRPC HealthStatusManager is also updated from the same coordinator.
4. Liveness is managed separately without automatically aggregating all dependency health into it.

Do not call the Actuator HTTP endpoint from inside the gRPC health handler on every probe if both live in the same process. Sharing state/components avoids network round-trips and reduces latency.

## 13. Health service and security

Health endpoints can disclose service names or dependency states. Decide who may call them:

- Internal orchestrator probes may need simple and reliable access.
- Clients outside the cluster do not necessarily need detailed health of every service.
- Do not include sensitive information such as database hostnames, credentials, stack traces, or topology details in health responses.
- If using TLS/mTLS, probes must trust the certificate and present the appropriate identity.
- Do not let the health service be blocked by authorization policies meant for business RPCs if the orchestrator needs access; yet do not expose internal details more broadly than necessary.

Health status should return only a concise signal: SERVING or NOT_SERVING with the service name. Root-cause details belong in protected logs, metrics, and diagnostic endpoints.

## 14. Observing health and avoiding false states

Health checks are part of observability, but do not replace metrics/logs/traces. Monitor:

- Ratio of probes returning SERVING vs. NOT_SERVING.
- Number of readiness state transitions.
- Time spent in NOT_SERVING state.
- Health RPC errors by status code.
- Check latency and Watch stability.
- Dependency health and last-checked timestamp.
- Number of instances removed from traffic.

Avoid rapidly toggling status back and forth when a dependency flaps. You can use failure thresholds, recovery thresholds, or stabilization windows before transitioning status. However, hysteresis must not delay stopping traffic when the service genuinely cannot handle requests safely.

A SERVING status is a commitment by the application. If the application sets status once at startup and never updates it when the database loses connectivity, the health service returns stale signals and misleads callers.

## 15. Testing health properly

### Testing the status manager

Tests must verify that the service transitions status across its lifecycle. The closest-to-contract approach is to build an in-process server with the health service registered, then invoke Health/Check using the generated health stub:

```java
HealthStatusManager manager = new HealthStatusManager();
manager.setStatus(
        "catalog.v1.CatalogService",
        ServingStatus.NOT_SERVING);

Server server = InProcessServerBuilder.forName(serverName)
        .directExecutor()
        .addService(manager.getHealthService())
        .build()
        .start();

ManagedChannel channel = InProcessChannelBuilder
        .forName(serverName)
        .directExecutor()
        .build();

HealthCheckResponse response = HealthGrpc
        .newBlockingStub(channel)
        .check(HealthCheckRequest.newBuilder()
                .setService("catalog.v1.CatalogService")
                .build());

assertEquals(ServingStatus.NOT_SERVING, response.getStatus());
```

In a complete test, place channel and server inside JUnit lifecycle hooks or try/finally, and always shut down and await termination. Then call manager.setStatus(..., SERVING) and verify Check returns the new status.

### Testing Watch

Verify Watch sends the initial status and subsequent changes after the manager updates status. Use a latch with a timeout to wait for callbacks; do not use arbitrary sleeps or infinite waits.

### Testing Spring integration

Start the Spring application context and verify:

- The health service is registered on the right gRPC server.
- Initial status is NOT_SERVING.
- After the readiness gate, status transitions to SERVING.
- When a mandatory dependency is unhealthy, status transitions per policy.
- When shutdown begins, status transitions to NOT_SERVING before the server stops accepting calls.
- An open TCP port with health status NOT_SERVING is still evaluated by probes as not ready.

### Testing transport

Use separate TCP/TLS tests to verify certificates, authority, network routes, and proxies. Do not substitute in-process tests for transport tests, because in-process does not create sockets or TLS handshakes.

## 16. Common errors

| Symptom | Cause | How to fix |
|---|---|---|
| Port open but business RPCs fail | Only using TCP probes | Call the gRPC health service and verify readiness |
| Health returns SERVING right when process binds port | Status set too early | Start at NOT_SERVING, update after readiness gate |
| Health stays SERVING when mandatory database is down | Status is not updated with dependencies | Use a readiness coordinator and dependency state |
| Database outage restarts all instances | Liveness depends on database | Separate liveness from readiness |
| Health RPC returns UNIMPLEMENTED | Health service not registered or server lacks method | Register standard health service |
| Probe queries wrong service name and receives NOT_FOUND | Used Java package or wrong Protobuf service name | Use full Protobuf service name |
| Probe times out even though server is healthy | Deadline too short, blocked workers, or heavy probe load | Set reasonable budgets and keep health handlers lightweight |
| Watch does not receive new status | Client handles stream improperly or server did not update manager | Test lifecycle and reconnects |
| Health flaps | Dependency probe lacks thresholds/hysteresis | Stabilize state transitions per policy |
| Health endpoint leaks topology | Response/logs contain internal details | Publish only minimal status, protect diagnostics |

## 17. Hands-on exercise

**Scenario:** The Catalog gRPC server binds port 9090 as soon as the process starts. The Spring application needs to connect to the database before serving GetProduct. Currently TCP probes report healthy even when the database is not ready yet.

Carry out the following:

1. Add grpc-services on the same release line as the gRPC Java runtime.
2. Register HealthStatusManager.getHealthService() on the same gRPC server as the Catalog service.
3. Set overall and catalog.v1.CatalogService to NOT_SERVING at the start of startup.
4. Create a readiness coordinator monitoring database readiness with a finite timeout.
5. Transition Catalog and overall status to SERVING only after mandatory dependencies are ready.
6. When the database loses serving capability with no fallback, transition status back to NOT_SERVING per policy.
7. When shutdown begins, transition status back to NOT_SERVING before stopping the server.
8. Write Check tests for overall and service-specific status; write Watch tests for transitions.
9. Keep liveness independent of the database to avoid restart storms.
10. Run separate TCP/TLS integration tests and prove that an open port does not mean health status is SERVING.

**Completion criteria:** the health service is registered on the right listener; status reflects lifecycle and dependency readiness; an unready service receives no traffic; liveness does not depend on transient dependencies; Check/Watch have tests; probes do not generate load or leak sensitive information.

## 18. Remember

An open TCP port only confirms there is a listener, not that the Spring gRPC service is ready. TLS handshakes and HTTP/2 connections also only verify transport. Use the gRPC Health Checking protocol with Check for periodic probes and Watch for continuous updates; manage status by full Protobuf service name and the empty overall service. Start at NOT_SERVING, transition to SERVING after the readiness gate, then return to NOT_SERVING before shutdown. Readiness can depend on mandatory dependencies; liveness should focus on process survivability to prevent restart storms. Health handlers must be lightweight, have timeouts, disclose no internal details, and be tested via the generated health stub. Add TCP/TLS integration tests for transport; do not use port-open as the sole criterion for health.

# Testing Health Transitions

The gRPC Health service publishes the serving status of the entire server or individual services. That status changes over the application lifecycle: during startup, when an essential dependency loses connectivity, upon recovery, and when the server begins shutting down. A test that only calls Health/Check once and receives SERVING does not prove the health implementation is correct; you must test the entire transition sequence and when clients observe those changes.

In Spring gRPC, health transitions must reflect the true readiness of services registered on the server. This lesson focuses on the state model, HealthStatusManager, differences between unary Check and streaming Watch, in-process tests, Spring lifecycle integration, handling dependency changes, and testing shutdown/probes.

## 1. What is a health transition?

A health transition is a published status change when serving conditions change. For example, with OrderService:

```text
STARTING
   |
   | configuration + dependencies + service initialization complete
   v
SERVING
   |
   | mandatory database becomes unavailable
   v
NOT_SERVING
   |
   | dependency recovers and readiness checks pass
   v
SERVING
   |
   | graceful shutdown begins
   v
NOT_SERVING
```

The health protocol does not have a dedicated STARTING enum. When a service is not yet ready, the application typically publishes NOT_SERVING or withholds publishing status so probes do not mistakenly believe the service is ready. Once serving conditions are met, the application transitions to SERVING.

A proper transition must satisfy:

- Status reflects actual conditions, not merely that the process is alive.
- Transitions to NOT_SERVING early enough to stop receiving new traffic.
- Returns to SERVING only after readiness prerequisites have recovered.
- Updates consistently for the service name that probes/clients check.
- Does not emit duplicate transitions or flip status due to stale late-arriving callbacks.

## 2. Distinguishing server status and per-service status

A health request has a service field. The empty string typically represents overall server status; a full name such as acme.orders.v1.OrderService represents a specific service.

A single server can host multiple services with different readiness requirements:

| Service | Readiness condition | Example status |
| --- | --- | --- |
| OrderService | Orders database and schema are ready | SERVING |
| InventoryService | Inventory store and required cache are ready | NOT_SERVING |
| Reflection | Registered per environment policy | Does not necessarily reflect business readiness |
| Overall server (empty string) | Application aggregation policy | Determined by the readiness coordinator |

Do not assume that overall server SERVING means every service is SERVING. Define clear aggregation semantics: whether the server is ready only when all mandatory services are ready, or still accepts traffic if an optional service is NOT_SERVING.

Tests should call Check for both specific service names and the empty string. If you only check overall status, failures in updating an individual service can be missed.

## 3. Check and Watch observe transitions differently

The standard health protocol has two RPCs:

- Check: unary RPC, returns a snapshot of the status at the moment the request is processed.
- Watch: server-streaming RPC, sends the current status and then sends updates whenever the status changes.

Check suits periodic probes such as Kubernetes. Watch suits clients wanting to receive changes without continuous polling.

When testing Watch, verify:

1. The client receives the current status immediately after subscribing to watch.
2. When the manager transitions status, the client receives the new status.
3. Transitions are observed in order.
4. When the client cancels or disconnects, the stream is released.
5. Do not assume Watch completes automatically after the first response; it is a long-lived stream.

For a service name unknown to the health manager, Check typically ends with RPC status NOT_FOUND; Watch can send the SERVICE_UNKNOWN enum. Do not confuse the response enum with the RPC status code.

## 4. Modeling readiness so tests are predictable

Avoid scattering health status updates across many beans or callbacks. Create a single coordinator that receives signals from lifecycle and dependency monitors and decides the published status.

Example internal states:

| Internal state | Condition | Health output |
| --- | --- | --- |
| STARTING | Initialization not yet complete | NOT_SERVING |
| READY | All mandatory prerequisites satisfied | SERVING |
| DEGRADED | A mandatory dependency is lost and the service cannot process requests | NOT_SERVING |
| RECOVERING | Dependency has reconnected but readiness checks have not completed | NOT_SERVING |
| STOPPING | Graceful shutdown in progress | NOT_SERVING |

Internal states can be richer than the health protocol enum. For example, DEGRADED might still map to SERVING if the service can still fulfill its full contract in degraded mode; that decision must be defined by business requirements and tested.

The coordinator should:

- Receive dependency events from a health monitor/circuit breaker instead of having each RPC mutate status directly.
- Synchronize updates when multiple dependencies change concurrently.
- Ignore stale callbacks if a newer transition has already occurred.
- Not mark SERVING simply because a TCP connection to a dependency just reopened; require a passing readiness check.
- Keep readiness calculation logic independent of restart/liveness logic.

## 5. Registering HealthStatusManager in grpc-java

HealthStatusManager in the grpc-services artifact manages status and provides the service implementation. You can initialize the initial status before registering the service:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;

final String ORDER_SERVICE = "acme.orders.v1.OrderService";

HealthStatusManager health = new HealthStatusManager();
health.setStatus("", ServingStatus.NOT_SERVING);
health.setStatus(ORDER_SERVICE, ServingStatus.NOT_SERVING);

Server server = ServerBuilder.forPort(9090)
    .addService(new OrdersService())
    .addService(health.getHealthService())
    .build()
    .start();

// After readiness prerequisites are satisfied:
health.setStatus(ORDER_SERVICE, ServingStatus.SERVING);
health.setStatus("", ServingStatus.SERVING);
```

This is a grpc-java example illustrating the API. In a Spring gRPC starter, register health.getHealthService() through the server configuration hook or BindableService mechanism supported by your version. Do not spin up a secondary server just so health status can be updated; probes must query the exact server receiving business RPCs.

When dependency events occur, the coordinator calls setStatus(serviceName, status) according to the readiness policy. When shutdown begins, transition services that must stop accepting traffic to NOT_SERVING before completing graceful shutdown.

## 6. Unit testing state transition logic

Unit tests should verify the coordinator's state transition table without needing to start a gRPC server:

| Current state | Event | Next state | Health output |
| --- | --- | --- | --- |
| STARTING | Initialization complete, dependencies ready | READY | SERVING |
| STARTING | Startup dependency check fails | STARTING or DEGRADED per policy | NOT_SERVING |
| READY | Mandatory dependency unavailable | DEGRADED | NOT_SERVING |
| DEGRADED | Dependency reconnects but probe has not passed | RECOVERING | NOT_SERVING |
| RECOVERING | Readiness checks pass | READY | SERVING |
| READY | Shutdown requested | STOPPING | NOT_SERVING |
| STOPPING | Late stale readiness callback arrives | STOPPING | Keep NOT_SERVING |

Key assertions:

- Each event produces the exact expected health output.
- Optional dependencies do not cause the service to lose readiness unless policy requires it.
- Stale callbacks do not move a service from STOPPING back to SERVING.
- Two dependencies changing concurrently do not lose updates.
- Repeated transitions to the same state do not cause unnecessary side effects.

Use a fake clock or controllable scheduler if readiness involves debounces, cooldowns, or timeouts. Avoid tests relying on long Thread.sleep() calls, which are flaky and slow down the suite.

## 7. In-process testing for Health/Check

An in-process server/channel tests the health service without needing a TCP port. The following example checks snapshots before and after transitions:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.health.v1.HealthCheckRequest;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.health.v1.HealthGrpc;
import io.grpc.protobuf.services.HealthStatusManager;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class HealthTransitionTest {
    private static final String ORDER_SERVICE =
        "acme.orders.v1.OrderService";

    private HealthStatusManager manager;
    private Server server;
    private ManagedChannel channel;

    @BeforeEach
    void setUp() throws IOException {
        String name = InProcessServerBuilder.generateName();
        manager = new HealthStatusManager();
        manager.setStatus(ORDER_SERVICE, ServingStatus.NOT_SERVING);

        server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(manager.getHealthService())
            .build()
            .start();
        channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    @Test
    void checkReflectsEachTransition() {
        HealthGrpc.HealthBlockingStub stub =
            HealthGrpc.newBlockingStub(channel);
        HealthCheckRequest request = HealthCheckRequest.newBuilder()
            .setService(ORDER_SERVICE)
            .build();

        assertEquals(
            ServingStatus.NOT_SERVING,
            stub.check(request).getStatus());

        manager.setStatus(ORDER_SERVICE, ServingStatus.SERVING);
        assertEquals(
            ServingStatus.SERVING,
            stub.check(request).getStatus());

        manager.setStatus(ORDER_SERVICE, ServingStatus.NOT_SERVING);
        assertEquals(
            ServingStatus.NOT_SERVING,
            stub.check(request).getStatus());
    }
}
```

The example assumes test dependencies include grpc-inprocess, grpc-services, compatible health protos, and JUnit 5. directExecutor() simplifies the test; if readiness code uses asynchronous executors, test with the real executor as well and synchronize completion before asserting.

This test proves Check reads manager state over gRPC. It does not prove that the Spring starter registered the health service or that lifecycle listeners invoked the coordinator at the right time; that requires a separate Spring integration test.

## 8. In-process testing for Health/Watch

Watch must send the initial snapshot and emit updates when status changes. You can use a BlockingQueue to receive statuses in order instead of sleeping for a fixed duration and guessing the callback ran:

```java
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

BlockingQueue<ServingStatus> updates = new LinkedBlockingQueue<>();
AtomicReference<ClientCallStreamObserver<HealthCheckRequest>> control =
    new AtomicReference<>();

ClientResponseObserver<HealthCheckRequest, HealthCheckResponse> observer =
    new ClientResponseObserver<>() {
        @Override
        public void beforeStart(
                ClientCallStreamObserver<HealthCheckRequest> requestStream) {
            control.set(requestStream);
        }

        @Override
        public void onNext(HealthCheckResponse response) {
            updates.add(response.getStatus());
        }

        @Override
        public void onError(Throwable error) {
            // The test can record errors for final assertion.
        }

        @Override
        public void onCompleted() {
            // Health Watch is typically a long-lived stream.
        }
    };

HealthGrpc.newStub(channel).watch(
    HealthCheckRequest.newBuilder()
        .setService(ORDER_SERVICE)
        .build(),
    observer);

assertEquals(
    ServingStatus.NOT_SERVING,
    updates.poll(2, TimeUnit.SECONDS));

manager.setStatus(ORDER_SERVICE, ServingStatus.SERVING);
assertEquals(
    ServingStatus.SERVING,
    updates.poll(2, TimeUnit.SECONDS));

control.get().cancel("test complete", null);
```

This is the test body using the server/channel created in the previous section's fixture. In a complete test, ensure control.get() is non-null before cancelling and check unexpected errors via a separate queue/latch. Never leave a Watch stream alive after a test; cancel it explicitly before shutting down the channel/server.

Do not assume every call to setStatus emits a new event if the status did not change. Tests should verify the required semantics: the initial snapshot and each distinct published status, without relying on event counts from repeated updates.

## 9. Testing unknown services and multiple services

Health transitions often fail on service names: the application updates OrderService while the probe queries the empty string or a different package. Add tests for:

- Check for a registered service name returns the exact status.
- Check for an unknown service returns NOT_FOUND.
- Watch for an unknown service behaves according to the chosen protocol/runtime.
- Updating OrderService does not inadvertently change InventoryService.
- Changing overall status does not overwrite individual service status unless policy requires it.
- Service names use the full proto package, not the Java package or Spring bean name.

With multiple services, build a test matrix across each service and state. Do not test only a single representative service if each service has different readiness dependencies.

## 10. Integrating transitions with the Spring lifecycle and dependencies

In Spring Boot, you can use ApplicationReadyEvent to trigger final readiness evaluation and ContextClosedEvent to transition state during shutdown. However, do not assume that merely receiving ApplicationReadyEvent means every dependency has achieved business readiness; the coordinator must still verify service prerequisites.

Example structure:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class GrpcHealthLifecycle {
    private final GrpcReadinessCoordinator readiness;

    GrpcHealthLifecycle(GrpcReadinessCoordinator readiness) {
        this.readiness = readiness;
    }

    @EventListener
    void onApplicationReady(ApplicationReadyEvent event) {
        readiness.evaluateAndPublish();
    }

    @EventListener
    void onContextClosed(ContextClosedEvent event) {
        readiness.markStopping();
    }
}
```

This is a skeleton illustrating the hooks. evaluateAndPublish() must complete mandatory readiness checks before publishing SERVING; markStopping() must synchronously update NOT_SERVING before the server stops accepting traffic. If the application has multiple contexts, filter events by the appropriate context to avoid a bean handling events from another context.

A dependency monitor or circuit breaker can emit events when the database/cache starts failing or recovers. Only dependencies affecting the ability to fulfill the contract should transition readiness to NOT_SERVING. Optional dependencies can be reflected via degraded metrics/alerts without necessarily pulling the service out of traffic.

## 11. Race conditions, debouncing, and shutdown

Readiness is often updated from multiple sources: startup callbacks, periodic checks, dependency events, and shutdown. Without coordination, several issues can occur:

- A SERVING callback arrives late after shutdown has begun.
- Two monitors overwrite each other's status.
- A flapping dependency causes health to toggle rapidly between SERVING and NOT_SERVING.
- A probe reads a snapshot right in the middle of a transition and a test assumes the wrong ordering.
- A Watch client is left behind, holding streams and resources after a test finishes.

Mitigations:

- Use a state machine or coordinator with synchronization/atomic transitions.
- Make STOPPING a terminal state for the instance lifecycle; subsequent readiness callbacks must never restore SERVING.
- Use bounded debounce/hysteresis to prevent flapping, without delaying NOT_SERVING too long when the service truly cannot serve.
- Distinguish a single health check timeout from a sustained dependency state.
- Use a fake clock/scheduler in unit tests for debouncing and retries.
- Verify shutdown order: publish NOT_SERVING, stop accepting new traffic, drain in-flight RPCs within the grace period, then close the server.

Health status does not replace graceful shutdown. It informs callers/probes that the instance is no longer ready; the server still needs to finish in-flight calls and shut down transport properly.

## 12. Test matrix and practice exercise

| Group | Scenario | PASS condition |
| --- | --- | --- |
| Initial state | Server just started, dependencies not ready | Check does not return SERVING |
| Startup complete | Prerequisites satisfied | Service transitions to SERVING |
| Dependency loss | Mandatory dependency unavailable | Service transitions to NOT_SERVING |
| Dependency recovery | Dependency reconnects but checks have not passed | Remains NOT_SERVING |
| Recovery complete | Readiness checks pass | Transitions back to SERVING |
| Per-service | Only Inventory fails | Order status is not changed outside policy |
| Overall status | A mandatory service loses readiness | Overall status follows aggregation rule |
| Watch | Client subscribes then status changes | Receives initial state and updates in order |
| Unknown service | Check wrong service name | RPC returns NOT_FOUND |
| Concurrent update | Multiple events arrive concurrently | Final state is consistent with no lost updates |
| Shutdown race | Readiness callback arrives after STOPPING | Does not revert to SERVING |
| Spring lifecycle | Context ready/closed | Coordinator updates at the right moment |
| Probe integration | Kubelet/monitoring calls endpoint | Right listener, service name, and network policy |

**Exercise:** An application has OrderService depending on the primary database and InventoryService depending on a cache. The database loses connectivity for 8 seconds and then recovers; the cache keeps working. While the database is recovering, the application begins graceful shutdown.

1. Define the state machine and aggregation policy for both services and the overall server.
2. Write unit tests for startup, database loss, pending recovery, completed recovery, and shutdown.
3. Write in-process Check tests to verify each service's independent status.
4. Write Watch tests verifying initial snapshot, transitions, and cancellation.
5. Create a race test proving a late recovery callback does not move the instance out of NOT_SERVING once STOPPING.
6. Integrate the readiness coordinator with the Spring lifecycle and dependency monitor.
7. Write integration tests against the Spring-managed server and verify the deployment environment's probe path.

**Self-check questions:**

- Why is a single Check test insufficient to verify health transitions?
- How do Check and Watch differ when status changes?
- Why does the health protocol not have a STARTING status?
- When should a dependency failure transition readiness to NOT_SERVING?
- How do you prevent stale callbacks from returning a service to SERVING after shutdown?
- Why must both service-specific and overall health be tested?
- How do you avoid using Thread.sleep() that makes Watch tests flaky?
- Why does health SERVING not replace business smoke tests?

**Remember:** Testing health transitions must verify initial state, dependency-driven changes, recovery, and shutdown. Use unit tests for the state machine, in-process Check/Watch tests for the protocol, and Spring integration tests for the real lifecycle. Centralize transition management, handle race conditions, and publish SERVING only once readiness prerequisites are met.

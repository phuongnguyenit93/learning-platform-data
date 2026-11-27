# Testing Health Checks

## Learning Objectives

After this lesson, you will be able to:

- Explain the purpose of the gRPC Health Checking Protocol and the Check/Watch RPCs.
- Register the health service on the same gRPC server alongside business services.
- Manage overall server and per-service health statuses using HealthStatusManager.
- Write integration tests over a real channel to verify SERVING/NOT_SERVING statuses.
- Test status transitions via Watch and handling of nonexistent services.
- Distinguish health/readiness from liveness and process state.
- Update health state during application startup, dependency loss, and shutdown.

## 1. What Problem Do Health Checks Solve?

A gRPC server can open a port and accept connections before it is ready to handle business traffic. For example, the Spring context may have started, but the database pool is not connected yet, caches have not warmed up, or a dependent service is unavailable. Conversely, one service may fail individually while other services on the same server continue working.

Health checking provides a standard protocol for clients, load balancers, or orchestration systems to ask whether a server is ready to serve traffic. With **SPRING_GRPC**, health status should reflect the actual ability of each service and the overall server to process RPCs.

Health checks do not replace monitoring, alerting, or deep dependency checks. They serve as a signal for traffic-routing decisions. A good health check must be fast, have clear semantics, and update whenever application state changes.

## 2. The gRPC Health Checking Protocol

gRPC defines a standard service in the **grpc.health.v1** package:

- **Check** is a unary RPC: the client queries the current status of a service.
- **Watch** is a server-streaming RPC: the server sends the initial status and subsequent updates whenever the status changes.

The request carries the full service name. For example, **acme.catalog.v1.CatalogService** is the Protobuf service name, not the Java class name or method name. An empty string represents the overall status of the server.

Key statuses:

| Status | Meaning |
| --- | --- |
| **SERVING** | The service is ready to receive and process requests. |
| **NOT_SERVING** | The service should not receive traffic right now. |
| **UNKNOWN** | The status is undetermined or not yet provided. |
| **SERVICE_UNKNOWN** | Used in Watch when the requested service is unknown to the health service. |

For Check, a nonexistent service is typically represented by the **NOT_FOUND** gRPC status. For Watch, the protocol uses **SERVICE_UNKNOWN** so the client knows the service name is not registered in the health registry. If the server does not install the health service, the client may receive **UNIMPLEMENTED**.

## 3. Distinguishing the Health Service from Business Services

The health service is an independent gRPC service with the service name **grpc.health.v1.Health**. It is registered on the same server as business services:

~~~text
gRPC server
  ├── acme.greeting.v1.GreetingService
  ├── acme.catalog.v1.CatalogService
  └── grpc.health.v1.Health
        ├── Check
        └── Watch
~~~

Clients call Health.Check or Health.Watch over the same endpoint and ManagedChannel as other services. The health service does not automatically know whether the application's database or dependencies are healthy; the application must update the status according to its readiness policy.

Nor does the health service automatically shield the endpoint from unauthorized clients. If your system requires the health endpoint to be accessible only to load balancers or monitoring agents, apply appropriate network policies or authorization interceptors.

## 4. Adding grpc-services and HealthStatusManager

In gRPC Java, the health implementation lives in the **grpc-services** artifact. Use a version compatible with the project's remaining gRPC dependencies, ideally managed centrally with a BOM/version alignment.

With Maven, the dependency usually looks like this; the version should be managed by the project's gRPC BOM:

~~~xml
<dependency>
    <groupId>io.grpc</groupId>
    <artifactId>grpc-services</artifactId>
</dependency>
~~~

**HealthStatusManager** holds server statuses and provides the service implementation to register:

~~~java
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;

HealthStatusManager healthStatusManager = new HealthStatusManager();

Server server = NettyServerBuilder.forPort(0)
    .addService(greetingService)
    .addService(catalogService)
    .addService(healthStatusManager.getHealthService())
    .build()
    .start();

healthStatusManager.setStatus("", ServingStatus.SERVING);
healthStatusManager.setStatus(
    "acme.greeting.v1.GreetingService",
    ServingStatus.SERVING);
healthStatusManager.setStatus(
    "acme.catalog.v1.CatalogService",
    ServingStatus.SERVING);
~~~

This snippet illustrates a self-managed server. In Spring gRPC, HealthStatusManager should be a bean whose lifecycle is tied to the server. If the starter already auto-configures the health service, use the starter's configuration API and do not register a second health service.

Set the overall status using an empty service name and set individual statuses for each monitored service. Do not use Java class names; use the full Protobuf service name.

## 5. Adding the Health Server to the Spring Test Context

If the starter does not manage the health service automatically, you can create a test fixture containing the business services and the health service. The fixture accepts the same HealthStatusManager bean so tests can update status while the server is running:

~~~java
final class HealthTestGrpcServer {
    private final List<BindableService> services;
    private final HealthStatusManager health;
    private volatile Server server;

    HealthTestGrpcServer(
            List<BindableService> services,
            HealthStatusManager health) {
        this.services = List.copyOf(services);
        this.health = health;
    }

    synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }
        ServerBuilder<?> builder = NettyServerBuilder.forPort(0);
        services.forEach(builder::addService);
        builder.addService(health.getHealthService());
        try {
            server = builder.build().start();
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot start gRPC health test server", ex);
        }
    }

    int port() {
        Server current = server;
        if (current == null || current.isShutdown()) {
            throw new IllegalStateException("gRPC server is not running");
        }
        return current.getPort();
    }

    synchronized void stop() {
        Server current = server;
        server = null;
        if (current == null) {
            return;
        }
        current.shutdown();
        try {
            if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                current.shutdownNow();
            }
        } catch (InterruptedException ex) {
            current.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Register the fixture and manager in test configuration:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class GrpcHealthTestConfiguration {
    @Bean
    HealthStatusManager healthStatusManager() {
        return new HealthStatusManager();
    }

    @Bean(initMethod = "start", destroyMethod = "stop")
    HealthTestGrpcServer healthTestGrpcServer(
            GreetingServiceImpl greeting,
            CatalogServiceImpl catalog,
            HealthStatusManager health) {
        return new HealthTestGrpcServer(
            List.of(greeting, catalog), health);
    }
}
~~~

Spring calls the init method after injecting dependencies and the destroy method when the context closes. The fixture binds a dynamic port and registers the health service exactly once. If the starter already registers the health service on its server, omit this fixture and use the configuration/port accessor provided by the starter; never start two servers for the same test.

## 6. Managing Health Status in Spring

A simple way to organize this is to inject HealthStatusManager into a component that manages readiness. When essential dependencies are ready, transition services to SERVING; when shutdown begins or a critical dependency becomes unavailable, transition to NOT_SERVING.

~~~java
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;
import org.springframework.stereotype.Component;

@Component
final class GrpcReadiness {
    private static final String GREETING =
        "acme.greeting.v1.GreetingService";
    private static final String CATALOG =
        "acme.catalog.v1.CatalogService";

    private final HealthStatusManager health;

    GrpcReadiness(HealthStatusManager health) {
        this.health = health;
    }

    void markReady() {
        health.setStatus(GREETING, ServingStatus.SERVING);
        health.setStatus(CATALOG, ServingStatus.SERVING);
        health.setStatus("", ServingStatus.SERVING);
    }

    void markCatalogUnavailable() {
        health.setStatus(CATALOG, ServingStatus.NOT_SERVING);
    }

    void markShuttingDown() {
        health.setStatus("", ServingStatus.NOT_SERVING);
        health.setStatus(GREETING, ServingStatus.NOT_SERVING);
        health.setStatus(CATALOG, ServingStatus.NOT_SERVING);
    }
}
~~~

This is an example of coordinating status; these methods should be invoked from corresponding application lifecycle hooks or events. Only call markReady after readiness conditions are genuinely met. Do not set all services to SERVING directly in a constructor while dependencies are still initializing.

With Spring, updates can be wired to application events or lifecycle components once dependencies are ready. When the context closes, update to NOT_SERVING before the server stops accepting traffic if the server lifecycle permits that ordering.

## 7. One Server, Multiple Service Statuses

If Greeting and Catalog rely on different dependencies, their statuses can differ:

| Event | Greeting | Catalog | Overall Server |
| --- | --- | --- | --- |
| All dependencies initialized | SERVING | SERVING | SERVING |
| Catalog database disconnects | SERVING | NOT_SERVING | Per system policy |
| Shared dependency unavailable | NOT_SERVING | NOT_SERVING | NOT_SERVING |
| Shutdown begins | NOT_SERVING | NOT_SERVING | NOT_SERVING |

The overall status is an application decision. If one critical service loses availability while others continue responding, you can keep the overall server SERVING and mark only the affected service NOT_SERVING. If the endpoint should only be considered ready when every service is working, the overall status must be NOT_SERVING.

Define a clear policy rather than automatically inferring overall status from an arbitrary service. Health checks do not replace routing by service name; clients should query the exact service they intend to call.

## 8. Testing Check Over a TCP Channel

Integration tests should call the health service over the same server and transport the application uses. The example below assumes the server fixture has registered HealthStatusManager and exposes a dynamic port:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.health.v1.HealthCheckRequest;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.health.v1.HealthGrpc;

@SpringBootTest
class GrpcHealthIntegrationTest {
    @Autowired
    HealthTestGrpcServer grpcServer;

    @Autowired
    HealthStatusManager healthStatusManager;

    private ManagedChannel channel;
    private HealthGrpc.HealthBlockingStub healthStub;

    @BeforeEach
    void connect() {
        healthStatusManager.setStatus("", ServingStatus.SERVING);
        healthStatusManager.setStatus(
            "acme.greeting.v1.GreetingService",
            ServingStatus.SERVING);
        healthStatusManager.setStatus(
            "acme.catalog.v1.CatalogService",
            ServingStatus.SERVING);

        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcServer.port())
            .usePlaintext()
            .build();

        healthStub = HealthGrpc.newBlockingStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @Test
    void reportsGreetingServiceAsServing() {
        HealthCheckResponse response = healthStub.check(
            HealthCheckRequest.newBuilder()
                .setService("acme.greeting.v1.GreetingService")
                .build());

        assertEquals(ServingStatus.SERVING, response.getStatus());
    }

    @AfterEach
    void closeChannel() throws InterruptedException {
        if (channel == null) {
            return;
        }
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }
}
~~~

The **HealthGrpc**, **HealthCheckRequest**, and **HealthCheckResponse** types are provided by the grpc-services/protobuf health API matching your gRPC Java version. Using a plaintext channel here is only for loopback tests without TLS; if the application exposes its health endpoint over TLS, test it with a dedicated TLS channel.

## 9. Testing Overall and Per-Service Statuses

Send Check with an empty service name to read the overall status:

~~~java
HealthCheckResponse overall = healthStub.check(
    HealthCheckRequest.getDefaultInstance());

assertEquals(ServingStatus.SERVING, overall.getStatus());
~~~

Next, check specific services using their full service names. Tests should verify that Catalog can be NOT_SERVING while Greeting remains SERVING if policy permits independent operation.

When a service name does not exist, Check typically terminates with **NOT_FOUND**. Testing this case catches typos or package/service name mismatches between client and server.

Do not only assert statuses at startup. Mutate the health manager during the test, call Check again, and verify the new status is reflected.

## 10. Testing Watch When Status Changes

Watch is a server-streaming RPC. The client receives the initial status and then receives updates as the server changes status:

Set Catalog to SERVING before opening Watch. The test needs to wait for the first status callback before switching to NOT_SERVING to avoid a race between registering Watch and changing status.

~~~java
healthStatusManager.setStatus(
    "acme.catalog.v1.CatalogService",
    ServingStatus.SERVING);

List<ServingStatus> updates = new CopyOnWriteArrayList<>();
CountDownLatch initial = new CountDownLatch(1);
CountDownLatch changed = new CountDownLatch(1);

HealthGrpc.newStub(channel).watch(
    HealthCheckRequest.newBuilder()
        .setService("acme.catalog.v1.CatalogService")
        .build(),
    new StreamObserver<>() {
        @Override
        public void onNext(HealthCheckResponse response) {
            updates.add(response.getStatus());
            if (updates.size() == 1) {
                initial.countDown();
            }
            if (response.getStatus() == ServingStatus.NOT_SERVING) {
                changed.countDown();
            }
        }

        @Override
        public void onError(Throwable error) {
            // Store error for assertion on the test thread.
        }

        @Override
        public void onCompleted() {
            // Watch typically stays open until the call is cancelled.
        }
    });

assertTrue(initial.await(2, TimeUnit.SECONDS));
healthStatusManager.setStatus(
    "acme.catalog.v1.CatalogService",
    ServingStatus.NOT_SERVING);

assertTrue(changed.await(3, TimeUnit.SECONDS));
assertEquals(
    List.of(ServingStatus.SERVING, ServingStatus.NOT_SERVING),
    updates);
~~~

This example assumes the initial status is SERVING with no intermediate transitions. In a complete test, store errors from onError in an AtomicReference and assert them on the test thread. Never rely on Thread.sleep() to guess when Watch has been registered.

Watch is typically a long-lived stream. After assertions finish, cancel the call or close the channel so observers and executors are not leaked into other tests. When a service name is unknown, Watch may emit SERVICE_UNKNOWN; tests should distinguish this from Check returning NOT_FOUND.

## 11. Readiness Is Not Liveness

**Readiness** answers the question: should this instance receive new traffic? **Liveness** answers: is the process still alive and capable of continuing to run?

An application may be NOT_SERVING because a database is temporarily unavailable while the process remains alive and able to recover. If liveness also fails under the same condition, the orchestrator may restart the instance repeatedly, making the dependency outage worse.

The gRPC health service is usually used as a readiness signal for clients/load balancers. Process liveness can be checked with a separate probe tailored to the deployment platform. Do not use a single status for all purposes.

## 12. Client Health Checking and Load Balancing

Some gRPC clients support built-in health checking via service config. When enabled, the client can open Watch for the configured service and treat a backend as healthy only when receiving SERVING. This helps load balancing by excluding unready backends from RPC selection.

Client health checking depends on implementation, version, and service config; not all clients automatically call Health.Check. If a client does not enable health checking, the health service still serves external probes/monitoring but does not prevent that client from sending requests to a NOT_SERVING backend.

Integration tests should verify the exact behavior of the client in use: health check service name configuration, Watch opened upon connecting, and NOT_SERVING backends excluded per policy. Do not assume that merely registering a health service makes all clients honor its status automatically.

## 13. Health Checks Must Be Fast and Safe

Do not execute fresh database queries or synchronous calls to multiple dependencies on every Check request if doing so can slow down the health endpoint and add load while the system is overloaded.

Usually, it is better to update readiness state when dependencies or lifecycle events change, then let Check read the managed state. If periodic dependency checks are required, use a health contributor/probe with timeouts and appropriate result caching; avoid creating a feedback loop where a health check calls the health endpoint itself.

Health endpoints can also reveal topology or internal state. Expose only the necessary level of detail, restrict access if required by policy, and never include exceptions, internal hostnames, or credentials in health responses.

## 14. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Forgetting to register the Health service | Client receives UNIMPLEMENTED | Add the health service to the starter/fixture-managed server. |
| Using Java class name instead of full Protobuf service name | Specific service Check is not found | Use the exact package + service name. |
| Updating only overall status | Clients querying a specific service get stale/missing status | Set statuses for each monitored service. |
| Marking SERVING before dependencies are ready | Traffic reaches an instance unable to serve requests | Update after the readiness gate. |
| Marking entire server NOT_SERVING when an unrelated service fails | Drops traffic for still-healthy services | Define policies per service and shared dependencies. |
| Treating readiness as liveness | Restart loops during temporary dependency outages | Separate traffic-readiness probes from process-liveness probes. |
| Not closing Watch in tests | Leaks streams and resources across tests | Cancel the call/channel after assertions. |
| Using Thread.sleep to wait for Watch | Flaky tests | Use latches/conditions with timeouts. |
| Assuming clients automatically use the health service | NOT_SERVING backends may still receive RPCs | Enable and test client health checking if needed. |

## 15. Hands-On Exercise

Create an integration test for a server with GreetingService and CatalogService:

1. Register the standard health service alongside both business services.
2. When the context is ready, set the overall status and both services to SERVING.
3. Call Check for the empty string, Greeting, and Catalog; verify statuses.
4. Change Catalog to NOT_SERVING and confirm Check reflects the new status.
5. Verify Greeting remains SERVING if policy allows independent operation.
6. Open Watch on Catalog, receive the initial status, and receive an update after changing status.
7. Call Check with a nonexistent service name and assert NOT_FOUND; test Watch for SERVICE_UNKNOWN if supported by the implementation per the protocol.
8. When shutdown starts, transition the required statuses to NOT_SERVING and verify clients no longer treat the instance as ready.
9. Close Watch, the channel, and the server according to the Spring test context lifecycle.

**Completion criteria:** the health service is called over real transport, overall and per-service statuses are accurate, Watch emits updates, unknown services are handled properly, and readiness updates with lifecycle events.

## 16. Takeaways

- The gRPC Health Checking Protocol provides unary Check and server-streaming Watch.
- Service names must be full Protobuf service names; an empty string represents overall status.
- Register the health service on the server and manage statuses with HealthStatusManager or the starter's equivalent mechanism.
- SERVING should only be set once the service is genuinely ready; switch to NOT_SERVING when it should not receive traffic.
- Check for an unknown service typically returns NOT_FOUND; Watch uses SERVICE_UNKNOWN.
- Readiness differs from liveness; a dependency failure does not necessarily mean the process needs restarting.
- Client health checking is not enabled automatically in every client; configure and test per actual implementation.
- Watch is a long-lived stream; tests must cancel calls/channels and use synchronization with timeouts.

Testing health checks ensures clients and load balancers receive accurate readiness signals per service, detect status changes, and remove unready instances from traffic flow.

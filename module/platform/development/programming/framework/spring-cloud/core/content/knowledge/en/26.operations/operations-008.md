# Shutting Down Applications Safely and Deregistering Before Exit

In a Spring Cloud system, an instance may be invoked through a service registry, Spring Cloud LoadBalancer, an API gateway, or a Kubernetes Service. If a process stops abruptly while the registry still advertises the instance as available, clients may keep sending requests to an address that has stopped accepting traffic. The typical outcome is connection errors, reset requests, or interrupted in-flight work.

A safe shutdown must coordinate three things: **stopping new traffic, completing in-flight work, and then deregistering the instance and closing resources**. Spring Boot provides graceful shutdown for web servers; Spring Cloud Commons provides `ServiceRegistry` and the auto-registration lifecycle; deployment platforms like Kubernetes manage stop signals and wait windows before forcing process termination.

This lesson belongs to the **Operations** chapter of the **SPRING_CLOUD_CORE** module. We will explore the shutdown lifecycle, pulling instances out of the service registry, coordinating readiness and traffic draining, completing in-flight requests, stopping consumers/schedulers, configuring Kubernetes, testing shutdown ordering, and troubleshooting common failures.

## 1. Learning Objectives

After this lesson, you can:

- Explain why an instance must be removed from traffic before the process exits.
- Distinguish readiness, liveness, service registry status, and process state.
- Enable graceful shutdown in Spring Boot and set timeouts based on real processing times.
- Use `ServiceRegistry` to update status or deregister a registration.
- Understand auto-registration and auto-deregistration in Spring Cloud Commons.
- Coordinate `REFUSING_TRAFFIC` readiness with registry `OUT_OF_SERVICE` status.
- Understand `SmartLifecycle` shutdown ordering and the `stop(Runnable)` callback.
- Design a drain step before Spring Boot stops the web server.
- Configure `preStop` and `terminationGracePeriodSeconds` in Kubernetes.
- Size wait windows based on registry propagation, load balancer caches, and in-flight requests.
- Close message consumers, schedulers, and connection pools in the proper order.
- Test successful shutdowns, timeouts, unavailable registries, and repeated operations.

## 2. Why Does Shutdown Need a Procedure?

Suppose `orders-service` has three instances advertised by Eureka. Load balancers hold the list of three instances and send requests to an instance about to be replaced with a new version.

If that instance merely receives `SIGTERM` and immediately closes the server, Eureka may retain the registration for some time. Clients caching the old address will keep picking that instance. New requests can fail even while the other two replicas are healthy.

A controlled shutdown procedure will:

1. Mark the instance as no longer accepting new requests.
2. Update the service registry so clients stop selecting the instance.
3. Wait for updates to propagate to the registry, discovery clients, and load balancers.
4. Stop accepting new connections and finish in-flight requests.
5. Stop consumers/schedulers and finish or hand off in-progress work.
6. Deregister the registration, close connection pools, threads, and resources.
7. Exit the process within the platform's allowed window.

~~~mermaid
flowchart TD
    A[Shutdown requested] --> B[Mark readiness REFUSING_TRAFFIC]
    B --> C[Mark registry OUT_OF_SERVICE]
    C --> D[Wait for discovery and LB propagation]
    D --> E[Spring Boot graceful web shutdown]
    E --> F[Finish in-flight HTTP requests]
    F --> G[Stop consumers and scheduled work]
    G --> H[Auto-deregister service registration]
    H --> I[Close clients and resources]
    I --> J[Process exits]
~~~

Exact step ordering may differ by service registry and runtime platform. What must hold is giving clients a chance to drop the instance from traffic before the endpoint stops serving, and giving in-flight work time to finish before the process is forcefully killed.

## 3. Distinguishing Readiness, Liveness, and Registry Status

These three states serve different purposes:

| State | Question Answered | Consumer |
| --- | --- | --- |
| Readiness | Should this instance accept new traffic? | Kubernetes Service, load balancer, platform probes |
| Liveness | Can this process keep running? | Kubernetes restart policy, orchestration |
| Service registry status | Should discovery clients select this instance? | Eureka, Consul, Zookeeper, or other registries |

When draining begins:

- Readiness transitions to `REFUSING_TRAFFIC`.
- Registration may transition to `OUT_OF_SERVICE` or the provider's equivalent status.
- Liveness remains `CORRECT` while the application finishes requests.
- The process exits only after shutdown steps finish or the allowed timeout expires.

Do not use liveness to signal that an instance is draining. If liveness flips to unhealthy, Kubernetes may restart the process and cut short in-flight request completion. Readiness is the proper signal to stop sending new traffic to the instance.

Spring Boot publishes `AvailabilityChangeEvent` for readiness and liveness. When Actuator is used, these states can be exposed via health groups such as `readiness` and `liveness`.

## 4. Spring Boot Graceful Shutdown

Spring Boot supports graceful shutdown for web applications using embedded Tomcat, Jetty, or Reactor Netty. When the application context closes, the web server stops accepting new requests and grants active requests a grace period to finish.

In newer Spring Boot versions, graceful shutdown is enabled by default. To declare the behavior explicitly and readably in deployment environments, you can configure:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s
~~~

`server.shutdown: graceful` instructs the web server to shut down in a controlled manner. `spring.lifecycle.timeout-per-shutdown-phase` sets the maximum duration per `SmartLifecycle` shutdown phase. When the timeout expires, Spring proceeds with context closing; do not assume long-running requests are held indefinitely.

### 4.1. What Happens to HTTP Requests?

During graceful shutdown:

- The server stops accepting new requests per embedded server mechanics.
- In-flight requests are given a chance to complete.
- Persistent connections and specific protocols can affect how new requests are rejected.
- Once the timeout elapses, shutdown proceeds even if requests remain unfinished.

Tomcat, Jetty, and Reactor Netty may refuse new connections at the network layer. Response details vary by server and version. Therefore, test with the real server your application uses—especially if using streaming responses, WebSockets, long polling, or long-running requests.

### 4.2. Sizing Timeouts Based on Workload

Timeouts must exceed normal processing times for requests needing draining while staying within platform limits.

Example:

| Component | Example Budget |
| --- | ---: |
| Registry update and propagation window | 10 seconds |
| Completion of in-flight HTTP requests | 20 seconds |
| Stopping consumers/schedulers and finishing work | 15 seconds |
| Resource closing and safety margin | 10 seconds |
| Total deployment budget | 55 seconds |

This is only a budgeting example. Measure p95/p99 request durations, message processing times, and registry update delays in your real system to pick appropriate values.

`timeout-per-shutdown-phase` applies per lifecycle phase. If an application has multiple sequential stop phases, total context shutdown time can exceed a single phase timeout. The container platform must budget enough time for `preStop`, all shutdown phases, and safety margin combined.

### 4.3. Verifying Shutdown Triggers Properly

Spring Boot normally receives context shutdown signals when the process receives a termination signal such as `SIGTERM`. Some IDEs or direct process termination methods may not send the right signal, preventing graceful shutdown from running as expected.

In container environments, test by deleting a Pod or sending `SIGTERM` to the main process. Never conclude graceful shutdown works merely from clicking Stop in an IDE.

## 5. ServiceRegistry in Spring Cloud Commons

Spring Cloud Commons provides the `ServiceRegistry` interface to manage instance registrations:

~~~java
public interface ServiceRegistry<R extends Registration> {

    void register(R registration);

    void deregister(R registration);

    void close();

    void setStatus(R registration, String status);

    <T> T getStatus(R registration);
}
~~~

`Registration` is a marker interface. Each implementation provides its own registration type and status vocabulary:

| Registry | Common Registration | Notes |
| --- | --- | --- |
| Eureka | `EurekaRegistration` | Supports `UP`, `DOWN`, `OUT_OF_SERVICE`, `UNKNOWN` |
| Consul | `ConsulRegistration` | Status depends on health checks and Consul implementation |
| Zookeeper | `ZookeeperRegistration` | Registration/deregistration behavior is implementation-dependent |

### 5.1. Updating Status Before Deregistering

`setStatus(registration, status)` lets you report that the instance no longer accepts traffic. For example, with Eureka, `OUT_OF_SERVICE` indicates the instance is registered but no longer serving normal requests.

~~~java
public final class RegistryDrainOperation<R extends Registration> {

    private final ServiceRegistry<R> serviceRegistry;
    private final R registration;

    public RegistryDrainOperation(
            ServiceRegistry<R> serviceRegistry,
            R registration) {
        this.serviceRegistry = serviceRegistry;
        this.registration = registration;
    }

    public void markOutOfService() {
        serviceRegistry.setStatus(registration, "OUT_OF_SERVICE");
    }

    public void deregister() {
        serviceRegistry.deregister(registration);
    }
}
~~~

This is a generic helper. When configuring beans in an application, use the concrete registration type for your active provider. Not every registry understands the string `"OUT_OF_SERVICE"`; verify valid statuses for your implementation before using them.

### 5.2. Auto-Registration and Auto-Deregistration

When a `DiscoveryClient` and service registry implementation are on the classpath, Spring Cloud can automatically register the local server. `@EnableDiscoveryClient` is no longer mandatory in modern configurations when auto-configuration detects the implementation.

Auto-registration can be disabled with:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Or use `@EnableDiscoveryClient(autoRegister = false)` in versions supporting that attribute. Disable auto-registration only when the application implements its own registration workflow.

In Spring Cloud Commons, the auto-registration lifecycle calls `ServiceRegistry.deregister(...)` on stop. `AbstractAutoServiceRegistration` currently implements stop lifecycle at phase `0` and performs deregistration followed by closing the service registry. This is an automatic cleanup mechanism; it does not create a propagation window before the web server begins graceful shutdown.

This implementation listens to `WebServerInitializedEvent` to register the service once the web server port is known. When the bean is destroyed, the cleanup callback invokes `stop`; `stop` deregisters the application registration, deregisters the management registration if registered, and closes the service registry. A `running` flag prevents repeated `stop` calls from deregistering twice.

If the management server runs on a separate port, check `spring.cloud.service-registry.auto-registration.register-management`. This property defaults to `true` in Spring Cloud Commons 5.0.4; set it to `false` if you do not want management endpoints advertised as a separate service.

### 5.3. Eureka unregister-on-shutdown

With Spring Cloud Netflix Eureka, the property:

~~~yaml
eureka:
  client:
    should-unregister-on-shutdown: true
~~~

lets the client actively unregister from Eureka during shutdown. This is the default in current configurations. Keep this option enabled if instances should self-deregister during normal shutdowns.

Do not rely on lease expiration as a substitute for active deregistration. Lease heartbeats and expiration exist to detect lost instances; they do not replace controlled draining.

## 6. Pulling Instances Out of Traffic Before Sending SIGTERM

Waiting solely for auto-deregistration during application context closing may leave too little time for the registry and discovery clients to refresh caches before the server stops accepting requests. A proactive drain step should run before `SIGTERM` is sent.

Recommended sequence:

1. Set readiness to `REFUSING_TRAFFIC`.
2. Update the service registry to a non-serving state, such as `OUT_OF_SERVICE` for Eureka.
3. Wait for the propagation window so the registry and clients/load balancers update.
4. Send `SIGTERM` so Spring Boot starts graceful shutdown.
5. Wait for in-flight requests and active work to finish.
6. Let Spring Cloud auto-registration deregister the registration and close the registry client.

Propagation is not always instantaneous. For example, Eureka clients currently have a default 30-second registry fetch interval; Spring Cloud LoadBalancer has a default 35-second cache TTL. These are defaults of the referenced versions, not mandatory wait durations for every system. Measure your provider/client's real cache chain and refresh cycle to determine the propagation window.

### 6.1. Setting Readiness to REFUSING_TRAFFIC

You can publish `AvailabilityChangeEvent` so Spring Boot updates readiness:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class ReadinessDrain {

    private final ApplicationContext applicationContext;

    public ReadinessDrain(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public void refuseTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.REFUSING_TRAFFIC);
    }
}
~~~

The readiness probe will reflect that the application is no longer ready to accept traffic. When Kubernetes uses the readiness probe from Spring Boot Actuator, the EndpointSlice controller can remove the Pod from the Service's ready endpoints.

### 6.2. Updating Registry Status

For registries supporting `OUT_OF_SERVICE`, you can call Spring Cloud Commons' Actuator endpoint if exposed and secured:

~~~bash
curl -fsS -X POST http://127.0.0.1:8080/actuator/serviceregistry \
  -H "Content-Type: application/json" \
  -d '{"status":"OUT_OF_SERVICE"}'
~~~

The endpoint requires a `Registration` bean in the application context. Valid statuses depend on the provider; Eureka supports `OUT_OF_SERVICE`, while Consul or Zookeeper may use different mechanisms.

Expose this endpoint only on management networks or loopback and require proper authorization. Never expose registry status mutation endpoints to the public Internet.

### 6.3. Combining Readiness and Registry Status in One Operation

In a control plane or drain service, execute both steps before stopping the process:

~~~java
public class InstanceDrainService<R extends Registration> {

    private final ReadinessDrain readinessDrain;
    private final RegistryDrainOperation<R> registryDrain;

    public InstanceDrainService(
            ReadinessDrain readinessDrain,
            RegistryDrainOperation<R> registryDrain) {
        this.readinessDrain = readinessDrain;
        this.registryDrain = registryDrain;
    }

    public void beginDrain() {
        readinessDrain.refuseTraffic();
        registryDrain.markOutOfService();
    }
}
~~~

If the registry update fails, emit logs/metrics and enforce an explicit policy. Strict systems may block shutdown until confirming the instance is no longer selected; environments prioritizing timely deployments may proceed after a timeout while accepting controlled risk.

A controller invoked by a platform hook can be very minimal:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal")
public class DrainController {

    private final InstanceDrainService<?> drainService;

    public DrainController(InstanceDrainService<?> drainService) {
        this.drainService = drainService;
    }

    @PostMapping("/drain")
    public ResponseEntity<Void> drain() {
        drainService.beginDrain();
        return ResponseEntity.accepted().build();
    }
}
~~~

This endpoint is an application-defined example, not a built-in Spring Cloud endpoint. Secure it with authentication/authorization and allow access only from the control plane or internal lifecycle hooks. Make the operation idempotent because orchestrators may retry requests.

## 7. SmartLifecycle Shutdown Ordering

Spring Framework allows components implementing `SmartLifecycle` to control startup and shutdown order. Lower phase values start earlier and stop later; higher phase values start later and stop earlier. When two beans share the same phase, relative order is not guaranteed. Explicit `depends-on` relationships can override phase ordering.

This matters because Spring Boot stops the embedded web server during an early graceful shutdown phase of context closing. Spring Cloud Commons auto-registration stops in its own phase and calls deregister. In the current implementation, `AbstractAutoServiceRegistration.getPhase()` returns `0`.

An operational consequence is: do not wait until the final auto-deregister step to start draining. Update readiness/registry state before sending the context close signal, or add a lifecycle hook with a higher phase than web server graceful shutdown to mark the instance out of traffic.

### 7.1. Using SmartLifecycle to Mark an Instance Before Web Server Shutdown

The following example runs a synchronous drain operation at a high lifecycle phase. `SmartLifecycle.DEFAULT_PHASE` is a high default phase value; in Spring Boot 4.1.2, `WebServerApplicationContext.GRACEFUL_SHUTDOWN_PHASE` has a lower value, so web server graceful shutdown runs after this lifecycle bean. Re-verify phase values for your active version when customizing lifecycles.

~~~java
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.springframework.context.SmartLifecycle;

public final class RegistryDrainLifecycle implements SmartLifecycle {

    private static final Log log =
            LogFactory.getLog(RegistryDrainLifecycle.class);

    private final InstanceDrainService<?> drainService;
    private volatile boolean running;

    public RegistryDrainLifecycle(InstanceDrainService<?> drainService) {
        this.drainService = drainService;
    }

    @Override
    public void start() {
        running = true;
    }

    @Override
    public void stop(Runnable callback) {
        try {
            drainService.beginDrain();
        }
        catch (RuntimeException exception) {
            log.error("Could not mark instance out of service before shutdown",
                    exception);
        }
        finally {
            running = false;
            callback.run();
        }
    }

    @Override
    public void stop() {
        stop(() -> { });
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return SmartLifecycle.DEFAULT_PHASE;
    }
}
~~~

The callback in `stop(Runnable)` must be invoked once the component finishes stopping. Failing to call the callback can make the lifecycle processor wait until timeout. This example logs errors and continues shutdown if the registry update fails; systems requiring strict guarantees may fail deployment or require operator intervention instead of swallowing errors.

### 7.2. Limitations of Lifecycle Hooks

A lifecycle hook executes actions within the same process, but does not by itself guarantee the registry has propagated the new state to all discovery clients. If a controlled propagation wait is needed, execute the drain step from the orchestrator or control plane before sending `SIGTERM`.

Do not place a long `Thread.sleep()` inside a lifecycle bean without accounting for it in the shutdown budget. A hung registry call or network timeout can consume the entire shutdown budget. Configure timeouts on registry client connections and bound the duration of drain operations.

## 8. Kubernetes: preStop and Termination Grace Period

Kubernetes follows its own Pod termination sequence:

1. The Pod is marked terminating.
2. Kubelet runs the `preStop` hook if configured.
3. After the hook completes, the container runtime sends the stop signal (typically `SIGTERM`) to the main process.
4. The process has until `terminationGracePeriodSeconds` expires to exit.
5. Once the grace period elapses, any remaining process may receive `SIGKILL`.

The grace period timer starts before `preStop` executes. Therefore, the hook and all of Spring's shutdown share this budget.

### 8.1. Exposing Readiness Probes

Example Actuator configuration:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - serviceregistry
~~~

Kubernetes can probe endpoints:

~~~text
/actuator/health/readiness
/actuator/health/liveness
~~~

Readiness transitions to unready when the application emits `AvailabilityChangeEvent` with `ReadinessState.REFUSING_TRAFFIC`. Liveness can remain healthy throughout draining.

### 8.2. Calling a Drain Endpoint from preStop

If the application exposes an authenticated internal endpoint to begin draining, you can invoke it in `preStop` followed by a brief propagation wait:

~~~yaml
spec:
  terminationGracePeriodSeconds: 75
  containers:
    - name: orders-service
      image: example/orders-service:1.0.0
      lifecycle:
        preStop:
          exec:
            command:
              - /bin/sh
              - -c
              - "curl -fsS -X POST http://127.0.0.1:8080/internal/drain && sleep 10"
~~~

This example uses `curl` and `sleep` for illustration. The image must contain those tools or invoke a dedicated executable. The drain endpoint must only be reachable from loopback/management networks and must be protected with appropriate authentication.

After the hook completes, kubelet sends `SIGTERM`. Spring Boot flips readiness to `REFUSING_TRAFFIC` during shutdown, stops accepting new requests, and finishes active requests within the graceful shutdown timeout.

### 8.3. Calculating terminationGracePeriodSeconds

For the example above, the budget should cover:

| Phase | Example |
| --- | ---: |
| `preStop` invokes drain and waits for registry propagation | 10 seconds |
| Spring Boot graceful shutdown | 25 seconds |
| Stopping consumers and closing resources | 15 seconds |
| Safety margin | 15 seconds |
| Total | 65 seconds |

Set `terminationGracePeriodSeconds` above the total budget, e.g., 75 seconds. These values are illustrative; measure your workload and choose realistic timeouts.

Kubernetes begins removing terminating endpoints from normal traffic routing while the process shuts down. EndpointSlice updates and Eureka/Consul deregistration are two separate mechanisms. If the application uses both Kubernetes Services and an external registry, drain both paths.

### 8.4. Avoid Abusing preStop Sleep

A brief wait helps propagation, but does not replace readiness or deregistration. Merely sleeping without marking the instance out-of-service still allows clients to keep sending requests during the wait.

Never extend `preStop` beyond what `terminationGracePeriodSeconds` allows. If the hook does not finish before the deadline, Kubernetes can still forcefully kill the container.

## 9. Stopping Consumers, Schedulers, and Background Work

HTTP graceful shutdown only handles web server traffic. A Spring Cloud application may also run Kafka/RabbitMQ consumers, schedulers, batch jobs, listeners, or asynchronous tasks.

Before exiting the process:

- Stop consuming new messages or pause consumers.
- Complete in-flight messages or roll back so the broker can redeliver.
- Commit offsets/acks only after successful processing per broker semantics.
- Stop scheduling new periodic jobs.
- Give running tasks time to finish or save checkpoints.
- Close clients and connection pools only after dependent work ends.

Never acknowledge a message before business processing completes just to shut down faster. For long-running consumers, design idempotency, retries, and dead-letter handling so messages can be safely reprocessed if the process is killed.

### 9.1. SmartLifecycle for Asynchronous Consumers

`SmartLifecycle.stop(Runnable)` suits components needing asynchronous shutdown. The callback is invoked only after the consumer has paused, completed, or handed off work per policy.

Example consumer control interface:

~~~java
import java.util.concurrent.CompletionStage;

public interface MessageConsumerControl {

    void start();

    CompletionStage<Void> pauseAndDrain();
}
~~~

~~~java
import java.util.concurrent.CompletionStage;
import org.springframework.context.SmartLifecycle;

public final class MessageConsumerLifecycle implements SmartLifecycle {

    private final MessageConsumerControl consumer;
    private volatile boolean running;

    public MessageConsumerLifecycle(MessageConsumerControl consumer) {
        this.consumer = consumer;
    }

    @Override
    public void start() {
        consumer.start();
        running = true;
    }

    @Override
    public void stop(Runnable callback) {
        CompletionStage<Void> stopped = consumer.pauseAndDrain();
        stopped.whenComplete((ignored, error) -> {
            running = false;
            if (error != null) {
                // Log the failure and rely on broker redelivery/idempotency policy.
            }
            callback.run();
        });
    }

    @Override
    public void stop() {
        stop(() -> { });
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return SmartLifecycle.DEFAULT_PHASE - 100;
    }
}
~~~

`MessageConsumerControl` is an illustrative application-defined interface; implementations must invoke the callback exactly once when draining finishes. Configure the consumer's phase so it stops before the clients it needs during draining, and before those clients are closed.

### 9.2. Closing Resources in Dependency Order

If a consumer needs a database or HTTP client to finish processing a message, those clients must stay active until the consumer finishes. Between two dependent components, the dependent component should stop before the component it depends on.

Spring `SmartLifecycle` stops in reverse phase order compared to startup. If A needs B running, B should have a lower phase than A so A stops before B. Explicit `depends-on` relationships also affect lifecycle ordering.

## 10. Idempotency, Retries, and Failure Scenarios

Shutdown may be requested multiple times: repeated `SIGTERM` signals, orchestrator retries, or an operator calling the drain endpoint before the process receives a signal. Drain operations must be idempotent.

| Scenario | Recommended Behavior |
| --- | --- |
| Already `OUT_OF_SERVICE` | Repeated requests cause no critical error |
| Registry unreachable | Log error, apply timeout, and follow explicit continue/abort policy |
| Cannot finish request within timeout | Stop at deadline; clients must retry safely |
| Consumer fails to drain in time | Nack/roll back or let broker redeliver; avoid premature ack |
| Deregistration fails | Log warning; rely on lease/health timeout as fallback |
| Process receives `SIGKILL` | No cleanup hook runs; rely on lease expiry and self-recovery |

Do not rely on `@PreDestroy` as the sole place for lengthy draining. By the time Spring begins destroying beans, the web server may already be in graceful shutdown or refusing requests. Operations needing propagation time should start from the control plane, `preStop`, or an appropriate lifecycle phase.

## 11. Testing Shutdown and Deregistration

Do not test only that a shutdown method is called. Tests must verify action ordering, lifecycle callbacks, registry status, and behavior when a step fails.

### 11.1. Testing RegistryDrainOperation

Example using Mockito to verify the instance is marked out-of-service before deregistering:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;

class RegistryDrainOperationTests {

    private static final class TestRegistration implements Registration {
    }

    @Test
    void marksOutOfServiceBeforeDeregistering() {
        ServiceRegistry<TestRegistration> registry =
                mock(ServiceRegistry.class);
        TestRegistration registration = new TestRegistration();

        RegistryDrainOperation<TestRegistration> operation =
                new RegistryDrainOperation<>(registry, registration);

        operation.markOutOfService();
        operation.deregister();

        var order = inOrder(registry);
        order.verify(registry)
                .setStatus(registration, "OUT_OF_SERVICE");
        order.verify(registry).deregister(registration);
    }
}
~~~

`TestRegistration` is a fake `Registration` implementation for tests. In real projects, use your provider's registration type or a simple fake.

### 11.2. Testing SmartLifecycle Callbacks

For lifecycle beans with asynchronous shutdown, verify the callback runs only after draining finishes:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class MessageConsumerLifecycleTests {

    private static final class FakeMessageConsumerControl
            implements MessageConsumerControl {

        private boolean pauseRequested;

        @Override
        public void start() {
        }

        @Override
        public java.util.concurrent.CompletionStage<Void> pauseAndDrain() {
            pauseRequested = true;
            return CompletableFuture.completedFuture(null);
        }

        boolean pauseRequested() {
            return pauseRequested;
        }
    }

    @Test
    void invokesStopCallbackAfterConsumerDrain() {
        FakeMessageConsumerControl consumer =
                new FakeMessageConsumerControl();
        MessageConsumerLifecycle lifecycle =
                new MessageConsumerLifecycle(consumer);

        lifecycle.start();
        AtomicBoolean callbackCalled = new AtomicBoolean(false);

        lifecycle.stop(() -> callbackCalled.set(true));

        assertThat(consumer.pauseRequested()).isTrue();
        assertThat(callbackCalled).isTrue();
        assertThat(lifecycle.isRunning()).isFalse();
    }
}
~~~

This test assumes the fake consumer completes draining synchronously. For real consumers returning futures, use a controllable future in the test to verify the callback has not run before future completion and runs exactly once afterward.

### 11.3. Testing Phase Ordering

Spring Framework stops `SmartLifecycle` beans in descending phase order. Write a small context test with fake lifecycle beans recording `stop` order and verify:

- The registry-marking lifecycle bean has a higher phase than the web server graceful phase.
- Consumers stop before databases/clients they rely on.
- Auto-registration still runs deregistration during context closing.

Do not hard-code every internal Spring Boot phase in application tests. Verify phase relationships among components your application configures and run integration tests on the real Spring Boot version.

### 11.4. Testing Behavior When Registry Fails

Simulate failures:

- `setStatus` times out or throws an exception.
- `deregister` fails because the registry is unavailable.
- `preStop` call to the drain endpoint fails.
- Consumers fail to finish before timeout.

Verify logs/metrics capture sufficient detail, callbacks are never dropped, the process obeys deadline policies, and unacknowledged messages can be redelivered.

## 12. Operational Runbook for Deploy or Scale-Down

A deployment runbook should be repeatable for every instance:

1. Select a replica to replace and confirm remaining replicas have sufficient capacity.
2. Invoke the drain operation or `preStop` to flip readiness to `REFUSING_TRAFFIC`.
3. Set registration to `OUT_OF_SERVICE` if supported by the provider.
4. Check registry status and readiness endpoint.
5. Wait for the propagation window based on discovery client and load balancer cache/refresh delays.
6. Send `SIGTERM` or let the orchestrator proceed with termination.
7. Monitor graceful shutdown logs, active requests, and consumer draining.
8. Verify registration has been deregistered or is no longer returned by discovery.
9. Verify the process exits before `terminationGracePeriodSeconds`.
10. Proceed to the next replica.

Never scale down all replicas simultaneously if the service lacks spare capacity or must preserve quorum. For stateful workloads, check leader election, partition ownership, distributed locks, and checkpoints before stopping an instance.

## 13. Troubleshooting

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Clients still call stopping instance | Registry has not received new status or clients hold stale caches | Mark out-of-service earlier and increase propagation window per measurements |
| Pod readiness failed yet Eureka shows UP | Kubernetes readiness and Eureka are independent mechanisms | Update both readiness and registry status |
| New requests reset during deploy | Server stopped before traffic drained or timeout too short | Remove instance from traffic before SIGTERM and enable graceful shutdown |
| Auto-deregister did not run | Auto-registration disabled, lifecycle bean missing, or process killed with SIGKILL | Check `spring.cloud.service-registry.auto-registration.enabled`, lifecycle logs, and termination deadline |
| Eureka retains instance after exit | Unregister failed or client disabled unregister-on-shutdown | Check `eureka.client.should-unregister-on-shutdown` and Eureka client logs |
| Kubernetes sends SIGKILL | `preStop` plus shutdown exceeded grace period | Increase budget, shorten shutdown work, or increase `terminationGracePeriodSeconds` |
| `preStop` cannot call endpoint | Image lacks `curl`, wrong port/path, or endpoint requires auth | Check image tools and management port/security config |
| Consumer loses messages | Acked before processing finished or lacks retry/idempotency | Ack after business commit; design redelivery and deduplication |
| Shutdown waits forever | `SmartLifecycle` omitted callback or network call lacks timeout | Call callback once and bound timeouts on all I/O operations |
| Instance still receives traffic over long-lived connections | Persistent connections, streaming, or client caches | Drain connections/sessions and test real protocols |
| Registry rejects `OUT_OF_SERVICE` | Provider uses a different status vocabulary | Use provider-specific status or health-check mechanism |
| Shutdown hook runs multiple times | Multiple triggers or repeated signals | Make operations idempotent and guard with atomic state |

### 13.1. Investigating a Failed Shutdown

1. Determine when the orchestrator requested termination and when `SIGTERM` was sent.
2. Check whether `preStop` finished completely.
3. Check whether readiness flipped to `REFUSING_TRAFFIC`.
4. Check whether the registry received `OUT_OF_SERVICE` and deregistered.
5. Compare registry update timestamp against the last request hitting the instance.
6. Check graceful shutdown logs and remaining in-flight requests.
7. Check whether consumers, schedulers, and async tasks finished.
8. Compare actual durations against `timeout-per-shutdown-phase` and `terminationGracePeriodSeconds`.
9. Identify whether `SIGKILL`, network timeouts, or a missing lifecycle callback occurred.

## 14. Practice Exercises

### Exercise 1 — Enable Graceful Shutdown

Configure `server.shutdown: graceful` and `spring.lifecycle.timeout-per-shutdown-phase`. Create a slow endpoint, send `SIGTERM`, and verify in-flight requests get time to finish.

### Exercise 2 — Deregister from the Service Registry

With Eureka, use `ServiceRegistry` or the Actuator endpoint to move the registration to `OUT_OF_SERVICE`. Verify discovery clients stop picking that instance.

### Exercise 3 — Coordinate Readiness and Registry

Publish `AvailabilityChangeEvent` with `ReadinessState.REFUSING_TRAFFIC`, then update the registry. Observe both states changing and measure propagation time.

### Exercise 4 — SmartLifecycle

Write a lifecycle hook that marks the registry before web server graceful shutdown. Verify phase, callback invocation, and behavior when the registry throws an exception.

### Exercise 5 — Kubernetes preStop

Add a `preStop` hook calling the drain endpoint and an ample `terminationGracePeriodSeconds`. Delete a Pod and verify readiness, EndpointSlices, registry status, and process termination.

### Exercise 6 — Consumer Drain

Create a consumer with long-running message processing. Pause new message consumption, finish active messages, then close the client. Verify no messages are lost on exit.

### Exercise 7 — Fault Injection

Simulate an unavailable registry, consumer timeouts, and requests exceeding the shutdown timeout. Record final states and propose an appropriate shutdown budget.

**Completion criteria:** you can drain an instance from discovery and traffic before stopping the process, complete active work within allowed time, and verify registrations and resources are cleaned up.

## 15. Summary

Safe shutdown in Spring Cloud coordinates the service registry, readiness, and Spring Boot's lifecycle. Before sending `SIGTERM`, switch readiness to `REFUSING_TRAFFIC`, update registration to a non-serving state if supported by the provider, and allow time for the registry/discovery/load balancers to update.

Spring Boot graceful shutdown stops accepting new requests and allows active requests time to finish within timeout. Spring Cloud Commons auto-registration deregisters registrations when the lifecycle stops; Eureka provides `should-unregister-on-shutdown` to actively unregister. `SmartLifecycle` orchestrates stop order and supports callbacks for asynchronous work. Kubernetes `preStop` can execute draining before `SIGTERM`, while its duration counts toward `terminationGracePeriodSeconds`.

Never rely on a single signal. Readiness, registry status, HTTP graceful shutdown, and consumer draining are separate parts of the same workflow. Test with real stop signals, measure timings, and ensure every operation has timeouts, idempotency, and clear error policies.

## References

- [Spring Boot 4.1.2 — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): graceful shutdown, rejecting new requests, and phase timeouts.
- [WebServerApplicationContext API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/server/context/WebServerApplicationContext.html): embedded web server graceful shutdown phase.
- [Spring Boot 4.1.2 — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): readiness/liveness states across shutdown phases and health probes.
- [Spring Boot 4.1.2 — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html): `AvailabilityChangeEvent`, `ReadinessState`, and `LivenessState`.
- [Spring Cloud Commons 5.0.4 — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `ServiceRegistry`, auto-registration, status endpoint, and discovery health.
- [Spring Cloud Commons 5.0.4 — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): auto-registration, management registration, and Spring Cloud LoadBalancer cache TTL.
- [Spring Cloud Netflix 5.0.3 — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html): `eureka.client.should-unregister-on-shutdown`.
- [AbstractAutoServiceRegistration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/serviceregistry/AbstractAutoServiceRegistration.java): lifecycle phase, stop, and deregistration.
- [ServiceRegistry source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/serviceregistry/ServiceRegistry.java): register, deregister, setStatus, and close contract.
- [Spring Framework 6.1 — SmartLifecycle](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html): phase ordering and asynchronous stop callback.
- [Kubernetes — Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/): preStop, SIGTERM, termination grace period, and SIGKILL.
- [Kubernetes — Explore Pod and Endpoint Termination Flow](https://kubernetes.io/docs/tutorials/services/pods-and-endpoint-termination-flow/): EndpointSlices and traffic draining during Pod termination.

Check your Spring Cloud release train, Spring Boot version, registry provider, and runtime platform before applying. Registry states, lifecycle phases, and graceful shutdown behavior can vary across release generations.

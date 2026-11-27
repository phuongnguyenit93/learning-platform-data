# Distinguishing Process Liveness, Application Readiness, and Serving Capability

## Objectives

After this lesson, you will be able to:

- Distinguish between process liveness, application readiness, and actual request serving capability.
- Understand Spring Boot's `LivenessState` and `ReadinessState`.
- Configure Spring Boot Actuator and Kubernetes health probes.
- Decide which dependencies should participate in readiness checks and which should not participate in liveness checks.
- Synchronize readiness with service discovery, load balancing, and the shutdown process.
- Design tests to detect instances that are still alive but cannot accept traffic or handle business logic.

## 1. Three Different Questions About Service State

When operating microservices, a single health signal cannot answer every question. Three concepts must be distinguished:

1. **Process liveness:** Is the process or JVM still operating in a way that the platform can continue using, or does it need to be restarted?
2. **Application readiness:** Has the instance finished initializing and can it accept new requests right now?
3. **Serving capability:** Can a specific request or operation complete with the currently available data, dependencies, permissions, and resources?

For example, a Spring Boot application may have a running JVM that has not yet finished connecting to the database. The process is alive, but the application is not ready to accept traffic. After readiness transitions to ACCEPTING_TRAFFIC, an inventory read request may still succeed while a payment request fails because the payment provider is experiencing an outage. Instance readiness does not guarantee that every operation will succeed.

| Concept | Question | Scope | Typical Corresponding Action |
| --- | --- | --- | --- |
| Liveness | Is the process still making progress and able to keep running? | Entire process/instance | On repeated failure, the platform may restart the container. |
| Readiness | Should the instance accept new requests? | Entire instance or traffic group | On failure, remove the instance from the target traffic pool. |
| Serving capability | Can this request be served? | Individual request, endpoint, or operation | Return an appropriate result, bounded retry, fallback, or controlled error. |

The three states are related but not interchangeable. An instance can be alive but not ready; it can be ready while a specific endpoint is failing; and a process can still exist while deadlocked so that requests are not processed.

## 2. Liveness: Should the Process Keep Running?

Liveness answers whether the instance has entered a broken state from which it cannot recover on its own. If liveness fails beyond a threshold, Kubernetes may restart the container. With Spring Boot, Actuator provides `LivenessStateHealthIndicator` and the `liveness` health group.

Spring Boot represents the state with:

- `LivenessState.CORRECT`: the application has not detected a broken liveness state.
- `LivenessState.BROKEN`: the application has detected a state in which it cannot continue operating safely.

Liveness is typically suited for detecting internal failures such as:

- An unrecoverable error that prevents the application from processing any more work.
- Corrupted internal state where the application needs a restart to recover.
- An application watchdog mechanism determining that a critical worker has died or cannot make progress.
- The application being stuck in a state where restarting is the designed recovery path.

Not every external dependency should be included in liveness. If the database, Redis, or an external API temporarily loses connectivity, restarting all pods simultaneously usually does not fix that dependency. Mass restarts can also increase connections, startup load, and pressure on an already struggling system.

Liveness should also not be a detailed business check. An overly heavy health endpoint can increase load or fail on its own when the system is overloaded. Keep liveness fast, local, and clearly meaningful.

## 3. Readiness: Is the Instance Ready to Accept Traffic?

Readiness answers whether the instance should be included in the target pool for new requests. Spring Boot provides:

- `ReadinessState.ACCEPTING_TRAFFIC`: the instance is ready to accept traffic.
- `ReadinessState.REFUSING_TRAFFIC`: the instance should temporarily not accept traffic.

Spring Boot Actuator exposes the `readiness` health group through `ReadinessStateHealthIndicator`. When the application finishes starting up, Spring Boot transitions to the ready state according to the default lifecycle. The application can also proactively change state in scenarios such as maintenance, warm-up, or shutdown.

Readiness can check the conditions truly required to accept requests:

- Initialization of critical configuration and components has completed.
- Connections to required databases have been established or pools are ready.
- Required caches have warmed up sufficiently to serve traffic.
- Critical consumers or workers have started if requests depend on them.
- The instance has not entered maintenance or draining mode.
- Resource headroom is sufficient to accept additional requests per operational policy.

Readiness does not necessarily have to check every dependency. If the application can still serve most requests when an auxiliary system is unavailable, putting that dependency into readiness can cause all replicas to be removed from traffic even though they remain capable of serving partial functionality.

### Instance-Wide Readiness vs. Per-Feature Capability

A readiness endpoint typically answers the instance-level question: should new traffic be routed to this pod? It does not replace dedicated health checks for individual dependencies or per-operation handling logic.

| Scenario | Appropriate Readiness | Request Handling |
| --- | --- | --- |
| Application has not finished loading required configuration | REFUSING_TRAFFIC | Do not accept requests yet. |
| Primary database is unreachable and all requests require the database | Can be REFUSING_TRAFFIC | Return a controlled error if requests still arrive while state is updating. |
| Email service is temporarily failing, but read APIs still work | Can remain ACCEPTING_TRAFFIC | Only the email-sending operation uses retry/outbox or returns a corresponding error. |
| Payment provider is failing, but order queries still work | Can remain ACCEPTING_TRAFFIC | The payment operation uses timeout, circuit breaker, and an appropriate response. |
| Request-serving thread pool is exhausted and the instance cannot accept more traffic | Can transition to REFUSING_TRAFFIC per policy | Bound the queue, return 429/503, or apply backpressure. |

Do not mark an instance NOT_READY just because a minor endpoint encounters an error. Define the service's serving contract and the minimum conditions for accepting new requests.

## 4. Serving Capability: Can a Specific Request Succeed?

Serving capability is the ability to execute a specific operation. It depends on multiple factors at request time:

- The dependencies required by that operation.
- Business data and state.
- Access permissions and caller identity.
- Timeouts, quotas, rate limits, and circuit breakers.
- Instantaneous resources such as thread pools, connection pools, queues, and memory.
- API version, schema, and data compatibility.

An instance can be READY while a payment request still fails due to a payment provider timeout. A catalog read request may still succeed. If readiness reflects the status of all dependencies for every operation, the system will easily evict too many instances and trigger a domino effect.

Serving capability should be reflected through request outcomes, metrics, tracing, dependency health, and protective mechanisms such as timeouts, circuit breakers, bulkheads, rate limits, and fallbacks. Do not turn every request error into an instance-wide readiness change.

Example controller returning results based on operation capability:

~~~~java
@RestController
@RequestMapping("/payments")
public class PaymentController {

    private final PaymentService paymentService;

    public PaymentController(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @PostMapping
    public ResponseEntity<PaymentResult> pay(
            @RequestBody PaymentCommand command) {
        try {
            return ResponseEntity.ok(paymentService.pay(command));
        } catch (PaymentProviderUnavailableException ex) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .build();
        }
    }
}
~~~~

If the payment provider is temporarily unavailable, the payment API can return 503 or an appropriate domain response. The instance can still serve other endpoints. This is operation-level handling, not necessarily a reason to restart the process.

## 5. Spring Boot Actuator Health Groups

Add Actuator to expose health endpoints:

~~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~~

Example configuration:

~~~~yaml
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
~~~~

When health probes are enabled, Spring Boot exposes the health groups:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

When `add-additional-paths` is supported and enabled, Spring Boot also exposes short paths on the main server port:

- `/livez`
- `/readyz`

Additional paths on the main application port are useful when the management server uses a separate port. If you only probe the management port, the health endpoint may still respond even if the main web server has failed or is not accepting requests. Exposing probe paths on the main server port checks the actual HTTP path the application uses to receive traffic.

Spring Boot may automatically enable probes when it detects a Kubernetes environment in some versions. Configuring `probes.enabled` explicitly makes behavior clearer across local, test, and Kubernetes environments. Check the documentation for the exact Spring Boot version in use.

### Health Groups Do Not Automatically Check Every Dependency

By default, the liveness and readiness groups focus on their respective availability states. Do not assume that every `HealthIndicator` in the application is included in both groups.

If you need to add an indicator to readiness, configure it explicitly:

~~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
~~~~

This example adds `db` to the readiness group. Use this only when the database is a mandatory condition for the instance to accept traffic. If the database fails and all pods transition to NOT_READY together, the Service may have no remaining endpoints; consider degradation options and how the system recovers.

Do not add `db`, Redis, a broker, or an external API to liveness just to restart pods when a dependency temporarily fails. If you must add an indicator, clearly understand whether a restart action can actually resolve that failure.

## 6. Proactively Changing Availability State

Spring Boot provides `ApplicationAvailability` to read state and `AvailabilityChangeEvent` to publish state changes. Example of transitioning an instance to refuse traffic when preparing for maintenance:

~~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;

@Component
public class MaintenanceMode {

    private final ApplicationContext applicationContext;

    public MaintenanceMode(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public void stopAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.REFUSING_TRAFFIC
        );
    }

    public void resumeTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.ACCEPTING_TRAFFIC
        );
    }
}
~~~~

Readiness state is managed by Spring Boot in the application context. The health group probe reads that state and reflects it in the HTTP status. Publishing the event does not itself stop the HTTP listener or cancel in-flight requests; it signals to the platform and routing layer that the instance should not receive new requests.

If the application uses a registry such as Eureka or Consul, configure the corresponding integration so readiness state is reflected in the registry when you also want the registry to stop selecting the instance. Changing Spring Boot's `ReadinessState` alone does not guarantee that every registry automatically updates its state.

## 7. Kubernetes Startup, Liveness, and Readiness Probes

Kubernetes provides three commonly used probe types:

| Probe | Purpose | On Failure |
| --- | --- | --- |
| startupProbe | Wait long enough for the application to start before evaluating liveness/readiness. | After the allowed number of failures, the container is restarted. |
| livenessProbe | Detect when a container is no longer operating normally. | Kubelet restarts the container according to policy. |
| readinessProbe | Determine whether the container should receive traffic from a Service. | The Pod is marked unready; the endpoint is not selected for normal Service traffic. |

When `startupProbe` is declared, Kubernetes does not run `livenessProbe` and `readinessProbe` until `startupProbe` succeeds. This is the right approach for applications that start slowly or need data warm-up.

Example Deployment:

~~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: inventory-service
  template:
    metadata:
      labels:
        app: inventory-service
    spec:
      containers:
        - name: app
          image: example/inventory-service:1.0.0
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
            failureThreshold: 3
~~~~

The values in the example are illustrative only. Tune `period`, `timeout`, `failureThreshold`, and `successThreshold` based on startup time, health endpoint latency, and failure-detection requirements. Do not set timeouts too short, which can cause false probe failures when the cluster is under heavy load.

Kubernetes HTTP probes treat response statuses in the range 200–399 as success. The Actuator health endpoint returns a status corresponding to the health group; when the group is DOWN or OUT_OF_SERVICE, Spring Boot typically returns HTTP 503 so the probe fails.

### How Does Readiness Probe Affect a Service?

When the readiness probe fails, the Pod may still be running, but it is not considered ready. Kubernetes updates endpoint status so the Service avoids sending normal traffic to unready Pods. With EndpointSlice, the `ready` condition reflects the endpoint's ability to accept traffic; certain settings such as `publishNotReadyAddresses` change endpoint publication behavior.

A readiness probe does not restart the container itself. If only readiness fails, the process keeps running so it can recover. Liveness is the probe that decides restarts upon repeated failure.

## 8. Connecting Readiness with Service Discovery

Service discovery can pull data from multiple sources: Kubernetes Endpoints/EndpointSlices, Eureka, Consul, or ZooKeeper. You must identify clearly at which layer readiness is reflected.

### Kubernetes Service and EndpointSlice

With a Kubernetes Service, Pod readiness affects which endpoints are used to route normal traffic. A `DiscoveryClient` reading Endpoints or EndpointSlices can see the set of instances based on endpoint state and how the implementation handles the ready condition.

Do not assume every discovery library filters endpoints identically to kube-proxy. Check the specific implementation and configuration, especially when `publishNotReadyAddresses` is enabled or when using a headless Service.

### Eureka

Eureka Client can integrate Spring Boot health status with the registry using:

~~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~~

Place this configuration in `application.yml` per the Spring Cloud Netflix guidance for the version in use. The documentation warns against placing this healthcheck property in `bootstrap.yml`, because the application state may not yet be initialized properly during bootstrap.

Health check integration allows the application's health status to be reflected in Eureka. However, do not assume by default that overall health status is strictly equivalent to `ReadinessState` or every business endpoint. If you want Eureka to advertise an instance only when readiness allows accepting traffic, check the `HealthCheckHandler` in use and customize the mapping if needed.

### Consul and Other Registries

Consul can use a health check attached to service registration, such as an HTTP check to an Actuator endpoint. Ensure the check path reflects readiness appropriately and the check interval does not introduce excessive lag. With ZooKeeper, registration is often tied to a session/ephemeral node; the mere existence of the session does not prove the application is ready to handle requests.

General principle: registry status, instance readiness, and health check results can have different latencies or semantics. Determine which source makes the final routing decision.

## 9. Startup, Warm-Up, and Registration Timing

An application typically goes through these stages:

1. The process/container is created.
2. The JVM and Spring ApplicationContext start up.
3. Beans, configuration, and connection pools are initialized.
4. The application warms up caches or loads required data.
5. Readiness transitions to ACCEPTING_TRAFFIC.
6. The instance is added to the traffic-receiving endpoint pool.
7. The application serves requests.

Not every registry waits for readiness before registering. A Eureka Client can register an instance when the application context finishes part of its lifecycle, while the application is still warming up. If the registry receives the instance too early, consumers may select an endpoint that cannot serve yet.

Ways to synchronize:

- Use a readiness probe so Kubernetes does not add the Pod to Service endpoints before it is ready.
- Configure registry health integration if you also want the registry to exclude unready instances.
- Control auto-registration or the registration lifecycle when the application has special startup requirements.
- Transition `ReadinessState` to ACCEPTING_TRAFFIC only after required conditions have completed.
- For cache warm-up, measure the duration and set `startupProbe` wide enough rather than lowering the readiness threshold too much.

Do not use fixed sleeps as a readiness mechanism. A fixed wait can be too short in slow environments and wasteful in fast ones. Check the actual conditions.

## 10. Graceful Shutdown and Draining

Readiness is not only important at startup. When an application is preparing to stop, it must stop accepting new requests before closing listeners or releasing resources.

A safe shutdown sequence:

1. Transition readiness to REFUSING_TRAFFIC.
2. Wait for Kubernetes/registry/load balancer to update endpoints.
3. Stop accepting new requests and let in-flight requests finish within a bound.
4. Deregister the instance from the registry if the registry integration requires it.
5. Close connection pools, consumers, and application resources.
6. Terminate the process before the termination grace period expires.

Spring Boot supports graceful shutdown:

~~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~~

In Kubernetes, set `terminationGracePeriodSeconds` long enough to cover preStop hooks, endpoint propagation, and shutdown phases. For example:

~~~~yaml
spec:
  terminationGracePeriodSeconds: 45
~~~~

These numbers must be tuned according to the longest request duration and routing propagation time. Spring Boot graceful shutdown stops accepting new connections according to what the server supports, but it does not guarantee by itself that the registry, ingress, service mesh, and all consumers have stopped sending requests. Test the entire path.

## 11. Do Not Abuse Health Checks

A good health endpoint should be fast, stable, and clearly meaningful. Some common design mistakes:

- **Liveness checking the database:** a temporary database failure causes all pods to restart, creating a restart storm.
- **Readiness checking every dependency:** a non-critical auxiliary system causes the entire service to be removed from routing.
- **Overly heavy probe endpoints:** the health check runs large queries or calls many external services, increasing load right when the system is weak.
- **Using a separate management port without understanding its limits:** the management server still responds even when the main HTTP server is not working.
- **Using the same endpoint for every probe:** liveness and readiness serve different purposes; sharing a combined endpoint can lead to unnecessary restarts.
- **Overly sensitive probes:** timeouts or failure thresholds that are too low cause a brief spike to trigger restarts or endpoint eviction.
- **Health checks without an authentication boundary:** endpoints expose internal details or get called excessively from outside.

Health endpoints should return only the minimum status needed, without stack traces, secrets, connection strings, or sensitive information. Restrict exposure and network access by environment.

## 12. Scenario Handling Matrix

| Scenario | Liveness | Readiness | Serving Capability |
| --- | --- | --- | --- |
| JVM is starting up | Not evaluated yet until startup probe succeeds if configured | REFUSING_TRAFFIC | Not serving requests yet |
| JVM is running, required cache not yet warmed up | CORRECT | REFUSING_TRAFFIC | Not accepting new traffic yet |
| Required database lost connectivity | Usually still CORRECT | Can be REFUSING_TRAFFIC if no DB-dependent requests can be served | DB-dependent requests fail; other operations may still work |
| Email provider is failing | CORRECT | Usually still ACCEPTING_TRAFFIC if core APIs can still serve | Email-sending operation uses retry/outbox or returns its own error |
| One business endpoint is failing | CORRECT | Usually still ACCEPTING_TRAFFIC | That endpoint returns a controlled error |
| Critical worker deadlocked, app cannot process work | Can be BROKEN if the app detects an unrecoverable state | REFUSING_TRAFFIC | Related requests cannot be served |
| Instance is in graceful shutdown | CORRECT until the process exits | REFUSING_TRAFFIC | Accepts no new requests, completes in-flight requests |
| Thread pool temporarily saturated | Usually still CORRECT | Can transition to REFUSING_TRAFFIC based on threshold and stabilization window | Backpressure, 429/503, or bounded queue |

The matrix is only a guideline. Actual states must follow the service contract, recovery behavior, and impact if an instance is restarted or removed from routing.

## 13. Observability and Testing

Track the following signals separately:

- Liveness probe failure count and container restart count.
- Readiness transitions between ACCEPTING_TRAFFIC and REFUSING_TRAFFIC.
- Time from process start to readiness.
- Number of ready endpoints in the Kubernetes Service/EndpointSlice or registry.
- Request rate, error rate, latency, and saturation per endpoint.
- Connection pools, thread pools, queue depth, and dependency state.
- In-flight request count during shutdown/draining.

Test scenarios:

| Scenario | Result to Verify |
| --- | --- |
| Slow startup | `startupProbe` protects the container from being restarted too early; readiness succeeds only after warm-up. |
| Temporary database outage | Liveness does not restart pods just because the DB fails; readiness accurately reflects serving capability per the service contract. |
| Optional dependency failure | The service continues accepting traffic if core operations can still be served. |
| Main HTTP server hung | Probes on the application port detect the failure instead of checking only a separate management port. |
| Thread pool saturation | Backpressure/metrics reflect saturation; readiness changes only according to the designed policy. |
| Rolling update | New pods receive traffic only after readiness; old pods stop accepting new requests before shutdown. |
| Graceful shutdown | In-flight requests are drained within the allowed time and the instance is removed from routing. |

Do not just check the HTTP status of the health endpoint. Verify the actual impact on Kubernetes endpoints, the registry, the load balancer, and requests from consumers.

## 14. Design Checklist

- [ ] Liveness reflects only internal errors that require a restart to recover.
- [ ] Do not put the database or external services into liveness by default.
- [ ] Readiness reflects the minimum conditions for an instance to accept new requests.
- [ ] Do not let an optional dependency make all replicas NOT_READY.
- [ ] Serving capability is handled per operation with timeouts, circuit breakers, backpressure, and appropriate errors.
- [ ] Enable Spring Boot Actuator probes and expose endpoints according to policy.
- [ ] Use `startupProbe` for slow-starting applications.
- [ ] Check probes via the main server port if you need to verify the real HTTP path.
- [ ] Synchronize readiness with the Kubernetes Service or registry if you want to control routing.
- [ ] Check `HealthCheckHandler` when integrating with Eureka.
- [ ] Transition the instance to REFUSING_TRAFFIC before graceful shutdown.
- [ ] Set the termination grace period long enough for endpoint propagation and request draining.
- [ ] Test dependency failures, slow startup, process hangs, saturation, and rolling updates.
- [ ] Monitor liveness, readiness, and request outcomes as separate signals.

## Key Takeaways

- Liveness asks whether the process should keep running; readiness asks whether the instance should receive new traffic; serving capability asks whether a specific operation can complete.
- Kubernetes restarts a container on repeated liveness failures; a failed readiness probe only marks the instance unready for normal traffic.
- Spring Boot represents states with `LivenessState` and `ReadinessState`, and exposes health groups via Actuator.
- Do not include every external dependency in liveness; doing so can cause a restart storm.
- Readiness should reflect core serving capability, not every optional feature.
- Registry state and readiness may not synchronize automatically; configure the appropriate integration.
- During shutdown, transition to REFUSING_TRAFFIC and drain requests before closing resources.
- Health probes are operational signals; request outcomes, metrics, and tracing are still necessary to evaluate true serving capability.

## Official References

- [Spring Boot – Actuator: Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot – Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability)
- [Spring Boot – Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Kubernetes – Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Kubernetes – Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Spring Cloud Netflix – Eureka Health Checks](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Commons – Service Registry](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)

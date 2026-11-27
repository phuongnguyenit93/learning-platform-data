# Warming Up an Application Before Publishing Serving Status

## 1. Why Application Warm-Up Matters

A Spring Boot process may have already started its web server without being ready to handle real load. The application may still need to create connection pools, load configuration, populate caches, warm up hot JVM execution paths, load models, or verify required dependencies.

If the service is advertised as ready as soon as its HTTP port opens, the registry or Kubernetes may route requests to the instance while it is still initializing. Users will experience timeouts, high latency, or dependency errors even though the application would eventually finish starting up.

**Warm-up** is the preparation phase before an instance accepts business traffic. In Spring Cloud Service Discovery, warm-up must coordinate with readiness state and instance status in the registry:

- The application has opened its port but still refuses new traffic.
- Preparation tasks run and are verified within bounded time limits.
- Only after warm-up succeeds is the instance advertised as ready.
- If warm-up fails, the instance remains unready or startup is marked as failed.

The goal is not to delay every startup. Only perform the steps needed so the first request can be processed safely and with acceptable quality.

## 2. Distinguishing Startup, Warm-Up, and Readiness

Lifecycle milestones are related but not synonymous:

| Milestone | Meaning | Should It Receive Business Traffic? |
|---|---|---|
| Process started | JVM and process are running | Not yet |
| Application context refreshed | Beans have been created and context configured | Not necessarily |
| Web server started | HTTP server has opened its port | Not necessarily |
| Warm-up running | Creating caches, connections, or preparing resources | Not yet |
| Warm-up completed | Required preparation steps have completed | Possible, after readiness is enabled |
| Ready / Accepting traffic | Application allows receiving new requests | Yes |

An application may be able to respond to a basic health endpoint while still not ready to process business logic. Therefore, an open TCP port or a live process should not be the sole condition for putting an instance into the registry.

~~~mermaid
flowchart TD
    START[Process starts] --> CONTEXT[Spring context initializes]
    CONTEXT --> SERVER[Web server opens port]
    SERVER --> REFUSE[Readiness: REFUSING_TRAFFIC]
    REFUSE --> WARM[Warm-up and dependency checks]
    WARM --> RESULT{Warm-up succeeded?}
    RESULT -->|No| HOLD[Keep unready state or fail startup]
    RESULT -->|Yes| READY[Readiness: ACCEPTING_TRAFFIC]
    READY --> PUBLISH[Advertise instance as serving]
    PUBLISH --> TRAFFIC[Receive business traffic]
~~~

Service registration order can vary by discovery provider. For example, auto-registration may run when the web server initializes, before `ApplicationRunner`s finish. Therefore, keep the instance in a non-serving state during warm-up rather than assuming registration will always occur after `ApplicationReadyEvent`.

## 3. Choosing What to Do During Warm-Up

Warm-up should be brief, bounded, and directly tied to request-serving capability. Common tasks include:

| Task | Purpose | Notes |
|---|---|---|
| Create connection pools | Prepare database or storage connections | Use timeouts and bound connection counts |
| Validate required configuration | Detect missing secrets, endpoints, or feature flags | Never print secrets to logs |
| Load reference data | Avoid forcing the first request to load baseline data | Load only what is needed |
| Populate critical caches | Reduce first-request latency | Enforce capacity limits and a stale policy |
| Load models or rules | Prepare processing resources | Verify checksum/version if needed |
| Initialize dependency clients | Catch DNS, TLS, or authentication issues early | Do not retry indefinitely |
| Run representative code paths | Warm up JIT or internal caches | Do not create business side effects |

What NOT to do during warm-up:

- Send real transactions or create irreversible business data.
- Scan entire large datasets just to warm a cache.
- Wait indefinitely on a non-essential dependency.
- Generate excessive concurrent load on databases or other services when multiple replicas start simultaneously.
- Write sensitive data to logs for diagnostics.

When multiple replicas start simultaneously, limit concurrency, use jitter, or coordinate the rollout to avoid warm-up causing a load spike on dependencies.

## 4. Controlling Readiness with Spring Boot

Spring Boot provides availability states to indicate whether an application should receive traffic. The two main readiness states are:

- **REFUSING_TRAFFIC:** the application is not ready to accept requests yet.
- **ACCEPTING_TRAFFIC:** the application is ready to accept requests.

Spring Boot can publish readiness state via `AvailabilityChangeEvent` and Actuator health groups. During normal startup, the application remains in the traffic-refusing state until `ApplicationReadyEvent` is published. Once `ApplicationRunner` and `CommandLineRunner` beans finish, Spring Boot transitions to the traffic-accepting state.

This works well when warm-up runs synchronously in a runner: the application does not become ready until the runner finishes.

### 4.1. Enabling the Readiness Health Endpoint

Example configuration:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
~~~

The readiness endpoint typically uses the path:

~~~text
/actuator/health/readiness
~~~

Kubernetes can call this endpoint in `readinessProbe`. When readiness state is `REFUSING_TRAFFIC`, the readiness health group reflects an unready state; after transitioning to `ACCEPTING_TRAFFIC`, the endpoint can return `UP` if other contributors also pass.

Do not use the liveness endpoint in place of readiness. Liveness answers whether the process needs to be restarted; readiness answers whether the instance should receive traffic.

### 4.2. Performing Synchronous Warm-Up with ApplicationRunner

`ApplicationRunner` runs after the `ApplicationContext` is initialized and before Spring Boot publishes `ApplicationReadyEvent`. This is an appropriate place for bounded-time synchronous warm-up:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ApplicationWarmupRunner implements ApplicationRunner {

    private final WarmupService warmupService;

    public ApplicationWarmupRunner(WarmupService warmupService) {
        this.warmupService = warmupService;
    }

    @Override
    public void run(ApplicationArguments args) {
        warmupService.prepareRequiredResources();
        warmupService.loadCriticalReferenceData();
        warmupService.exerciseRepresentativePath();
    }
}
~~~

In this example, the runner completes only when required warm-up steps finish. If a step throws an exception, startup can fail and the application does not transition to `ACCEPTING_TRAFFIC` readiness.

Warm-up operations must have timeouts and bounded retries. If warm-up may take several minutes or must run in the background, use a dedicated readiness gate to keep the application unready until the background task reports completion.

## 5. Readiness Gate for Asynchronous Warm-Up

Some tasks are unsuitable for blocking `ApplicationRunner`, such as loading a large dataset or initializing background resources. You can create a separate warm-up state and include its health indicator in the readiness group.

Example state coordinator:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class WarmupState {
    private final AtomicBoolean completed = new AtomicBoolean(false);

    public boolean isCompleted() {
        return completed.get();
    }

    public void markCompleted() {
        completed.set(true);
    }
}
~~~

Health indicator reflecting warm-up status:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("warmup")
public class WarmupHealthIndicator implements HealthIndicator {

    private final WarmupState warmupState;

    public WarmupHealthIndicator(WarmupState warmupState) {
        this.warmupState = warmupState;
    }

    @Override
    public Health health() {
        if (warmupState.isCompleted()) {
            return Health.up().build();
        }
        return Health.outOfService()
                .withDetail("phase", "warming-up")
                .build();
    }
}
~~~

Add the warmup contributor to the readiness group:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,warmup
  endpoints:
    web:
      exposure:
        include: health
~~~

The background task calls `markCompleted` only after all required steps succeed. If the task fails, the state remains incomplete and the Pod remains NotReady.

With an asynchronous approach, ensure warm-up is actually triggered and has timeout, retry, logging, and error-handling policies. If the default readiness indicator does not include warmup, the Pod may become Ready too early.

## 6. Keeping Instances Out of Service in Eureka

Kubernetes readiness and Eureka instance status are two separate mechanisms. A Kubernetes readiness probe does not automatically change instance status in Eureka unless the application integrates the two.

Eureka has statuses such as UP, DOWN, STARTING, OUT_OF_SERVICE, and UNKNOWN. During warm-up, you can keep the instance in OUT_OF_SERVICE or STARTING and then transition to UP once ready.

A common configuration is setting the initial status:

~~~yaml
eureka:
  instance:
    initial-status: OUT_OF_SERVICE
~~~

After warm-up completes, Spring Boot transitions readiness to `ACCEPTING_TRAFFIC`. You can listen for this availability event to synchronize Eureka status:

~~~java
import com.netflix.appinfo.InstanceInfo;
import com.netflix.discovery.EurekaClient;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class EurekaReadinessListener {

    private final EurekaClient eurekaClient;

    public EurekaReadinessListener(EurekaClient eurekaClient) {
        this.eurekaClient = eurekaClient;
    }

    @EventListener
    public void onReadinessChange(
            AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
            eurekaClient.setStatus(InstanceInfo.InstanceStatus.UP);
        } else if (event.getState() == ReadinessState.REFUSING_TRAFFIC) {
            eurekaClient.setStatus(InstanceInfo.InstanceStatus.OUT_OF_SERVICE);
        }
    }
}
~~~

Synchronous warm-up still runs in the `ApplicationRunner` from the previous section. This listener transitions Eureka to UP only when Spring Boot publishes `ACCEPTING_TRAFFIC` readiness; if readiness reverts to `REFUSING_TRAFFIC`, the instance is moved back to `OUT_OF_SERVICE`. The example illustrates custom integration with Eureka. Verify the `initial-status` property and client API appropriate for your Spring Cloud Netflix version. If auto-registration is disabled or a provider registers differently, adjust the register/status sequence accordingly.

If warm-up fails, do not transition the instance to UP. You can let startup fail so the platform restarts it, or keep `OUT_OF_SERVICE` and perform bounded retries according to operational policy.

### 6.1. Using Eureka Health Check Integration

Spring Cloud Netflix Eureka Client can integrate the application's health state into its published status:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

When health check integration is enabled, the application's health status can be used to update instance status in Eureka. You can build a dedicated `HealthIndicator` for warm-up and ensure it accurately reflects completion. If you also use a listener to update status manually, ensure the two status sources do not conflict; the health indicator must report an unready status until warm-up finishes.

Do not assume health check integration automatically understands every readiness state or includes every Actuator health group across all versions. Check how your version maps Health status to Eureka status and verify by querying the registry during warm-up.

If strict control over publication timing is needed, an initial status of `OUT_OF_SERVICE` combined with updating to UP after Spring Boot transitions to `ACCEPTING_TRAFFIC` is a clear approach. Health check integration can supplement this by reflecting health degradation after serving has begun, as long as health status and `setStatus` calls are coordinated consistently.

## 7. Combining Warm-Up with Consul

With Spring Cloud Consul Discovery, a service is typically registered alongside a health check. Consul can mark a service as passing, warning, or critical based on check results.

An illustrative HTTP health check configuration:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        health-check-path: /actuator/health/readiness
        health-check-interval: 10s
        register-health-check: true
~~~

If the readiness endpoint still reports unready during warm-up, Consul's health check can mark the instance as non-passing. Once warm-up finishes and the readiness endpoint returns UP, the next check can update the service status.

Distinguish service registration in the catalog from health check status. An instance may already appear in the catalog while still in critical state; clients must query passing services if they want only healthy instances.

The health check interval adds latency between warm-up completion and Consul marking the instance passing. If faster status transitions are needed, adjust the interval within the load and responsiveness limits of the health endpoint.

## 8. Warm-Up and Kubernetes Readiness

In Kubernetes, the readiness probe is the direct mechanism controlling whether a Pod is included in a Service's normal endpoints. A Pod can be Running throughout warm-up while remaining NotReady.

Example Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
    spec:
      containers:
        - name: payment-service
          image: example/payment-service:2.5.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
~~~

The startup probe gives the application initial startup time. The readiness probe continues keeping the Pod out of endpoints until warm-up finishes. The liveness probe should reflect only whether the process needs to be restarted.

When readiness transitions to succeeding:

1. The Pod Ready condition is updated.
2. The EndpointSlice controller updates endpoint conditions.
3. Service networking can add the Pod to the target pool for new traffic.
4. Ingress, gateways, or client discovery update their lists via their respective mechanisms.

Components maintain separate caches, so changes do not necessarily reach every client at the exact same instant.

## 9. Warm-Up and Registration Order by Model

There is no single order across all providers. Identify when auto-registration happens and how to keep instances non-serving before deploying.

| Model | How to Keep Instance Non-Serving | When to Allow Traffic? |
|---|---|---|
| Kubernetes Service | Readiness probe returns NotReady | When warm-up finishes and readiness returns UP |
| Eureka auto-registration | Initial status OUT_OF_SERVICE/STARTING or health integration | Transition status to UP after warm-up |
| Consul Discovery | Readiness health check is not yet passing | When health check transitions to passing |
| Self-managed ServiceRegistry | Do not register yet or register with non-serving status | Call register/setStatus after preparation finishes |

If an application both runs on Kubernetes and registers with Eureka, keep both states consistent. For example, a Pod that is NotReady while Eureka status is UP can still be discovered and called directly by clients outside Kubernetes.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Warm as Warmup Coordinator
    participant K8s as Kubernetes
    participant Reg as Eureka / Consul
    App->>K8s: Pod starts, readiness not yet met
    App->>Reg: Instance non-serving (OOS / health critical)
    App->>Warm: Start warm-up
    Warm->>Warm: Connect, load caches, verify resources
    Warm-->>App: Warm-up completed
    App->>K8s: Readiness transitions to UP
    App->>Reg: Instance status transitions to serving
    K8s-->>App: Endpoints updated gradually
    Reg-->>App: Registry/clients receive changes gradually
~~~

## 10. Designing Retries, Timeouts, and Warm-Up Failures

Warm-up is part of startup, so failures must be handled deliberately:

- Set separate timeouts for each dependency.
- Use bounded retries with backoff; avoid continuous tight retries.
- Distinguish required dependencies from optional ones.
- Log the step name, duration, and failure reason; never log secrets.
- Set a maximum total warm-up duration so rollouts do not hang indefinitely.
- If warm-up runs in the background, keep readiness in the traffic-refusing state until a final outcome is reached.
- If warm-up cannot recover, fail startup or keep the instance out of service and raise an alert.

When multiple replicas start concurrently, they can create a heavy burst of load on databases, caches, or configuration APIs. Use concurrency limits, jitter, and an appropriate rollout strategy to spread the load.

Do not use failed readiness as a way to hide permanent startup errors. Alert whenever a Pod or instance stays in the warming-up state for too long.

## 11. Observing Warm-Up Duration

Measure the duration of each step rather than just logging a single "application ready" line. Useful metrics:

| Metric | Meaning |
|---|---|
| **application_warmup_duration_seconds** | Total warm-up duration |
| **application_warmup_step_duration_seconds** | Duration of each preparation step |
| **application_warmup_success_total** | Number of completed warm-ups |
| **application_warmup_failure_total** | Number of failed warm-ups |
| **application_readiness_state** | Current readiness state |
| **service_registry_status** | Published instance status |

Metric names are illustrative conventions; use your monitoring system's naming conventions and instrumentation. Label by service and version, avoiding high-cardinality instance IDs if the metrics system is not suited for them.

To investigate slow rollouts, compare:

- Time from process start to web server start.
- Time from server start to warm-up completion.
- Time from warm-up completion to readiness UP.
- Time from readiness UP until the endpoint appears in Kubernetes or the registry transitions to passing/UP.

These milestones reveal whether latency lies in the application, probes, registry, or client-side caches.

## 12. Testing Warm-Up Behavior

A practical test suite should cover both success and failure cases:

1. Start the application with healthy dependencies; verify initial readiness is not yet met.
2. Inspect the registry to confirm the instance is not marked serving during warm-up.
3. Wait for warm-up to finish; verify readiness transitions to ACCEPTING_TRAFFIC or the health endpoint returns UP.
4. Check Eureka status, Consul passing state, or EndpointSlice ready condition accordingly.
5. Send business requests and confirm requests reach the instance after warm-up.
6. Force a required dependency to fail; confirm the application does not transition to serving state.
7. Test timeouts and bounded retries; ensure the application does not hang indefinitely.
8. If warm-up is asynchronous, verify the health indicator remains NotReady until the task completes.

| Scenario | Expected Outcome |
|---|---|
| Warm-up completes | Instance transitions to ready state |
| Required dependency unreachable | Instance receives no new traffic |
| Optional dependency fails | Application stays ready if business rules permit |
| Warm-up exceeds maximum duration | Alert fires or startup fails per policy |
| Pod deleted during warm-up | Pod is not treated as a ready endpoint |
| Eureka instance not yet warmed up | Status is not UP |
| Consul health check during warm-up | Service is not yet in passing state |

## 13. Common Design Mistakes

### 13.1. Using ApplicationReadyEvent to Start Warm-Up

`ApplicationReadyEvent` means runners have finished and the application is about to transition to ready state. If you only start warm-up on this event, readiness may already have transitioned to `ACCEPTING_TRAFFIC`. Perform synchronous warm-up in `ApplicationRunner`/`CommandLineRunner` or keep a separate readiness gate for background tasks.

### 13.2. Using Only Kubernetes Readiness and Forgetting Eureka

If an application uses both a Kubernetes Service and Eureka registration, the Pod may be NotReady while Eureka still advertises UP. Clients querying Eureka from outside the cluster can still call the instance. Keep status synchronized in both places.

### 13.3. Confusing Liveness with Readiness

Incomplete warm-up usually does not mean the process needs a restart. If liveness depends on warm-up state, kubelet may repeatedly restart the container and never give the application enough time to prepare.

### 13.4. Warm-Up Without Timeouts

A hung dependency can keep the application from ever becoming ready. Set timeouts, bounded retries, and alerts when warm-up duration exceeds thresholds.

### 13.5. Warm-Up Creating Business Side Effects

Sending real payments, creating orders, or publishing real messages to "warm up" can corrupt data. Run only safe, repeatable representative operations that produce no unintended side effects.

### 13.6. Assuming UP Status Means Every Client Has Updated

After the registry changes status, peer replication, health check intervals, and client caches still take time to update. Observe endpoints across layers instead of checking only a single dashboard.

## 14. Recommended Implementation Workflow

1. Identify required and optional warm-up steps.
2. Set timeouts, retries, and maximum total duration for each step.
3. Choose synchronous warm-up in `ApplicationRunner` or asynchronous warm-up with a readiness gate.
4. Enable the Spring Boot readiness health endpoint and configure appropriate probes.
5. If using Eureka, keep initial status non-UP and transition to UP only after warm-up; verify behavior on your exact version.
6. If using Consul, have the readiness health check reflect warm-up state and query only passing services when healthy instances are needed.
7. If running on Kubernetes, inspect EndpointSlices and ensure NotReady Pods do not receive new traffic.
8. Measure warm-up duration and latency from warm-up to endpoint publication.
9. Test dependency failures, restarts, rolling updates, and concurrent replica startups.

## 15. Summary

Warm-up prepares critical resources and execution paths before a service accepts traffic. Spring Boot can hold readiness at `REFUSING_TRAFFIC` while `ApplicationRunner` executes; for background tasks, a dedicated health indicator must keep readiness unready until warm-up finishes.

Kubernetes uses readiness probes to decide whether a Pod belongs in the serving endpoint pool. Eureka and Consul maintain their own registry/health statuses, so keep instances non-serving during warm-up and transition to UP or passing only after completion. When an application spans multiple discovery mechanisms, synchronize their states, configure timeouts and bounded retries, and measure latency at each step to avoid advertising instances too early.

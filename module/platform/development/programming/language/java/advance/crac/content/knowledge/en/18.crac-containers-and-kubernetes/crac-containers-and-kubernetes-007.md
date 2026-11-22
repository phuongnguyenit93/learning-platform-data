# Startup Probe, Readiness Probe, and Liveness Probe After Restore

Kubernetes uses three probe types to monitor the container lifecycle: **startup probe**, **readiness probe**, and **liveness probe**. Each probe answers a different question: whether the application has finished starting, whether it can receive traffic, and whether the process is still working properly.

When a Java application uses CRaC (Coordinated Restore at Checkpoint), these questions must be re-applied after the process is restored. A JVM may restore quickly from a checkpoint while still reconnecting to the database, loading secrets, opening HTTP clients, validating leases, or initializing background workers. If Kubernetes adds the Pod to a Service too early, requests may arrive before dependencies are ready. If the liveness probe treats a failed external dependency as a process liveness failure, the kubelet may repeatedly restart the container and make the situation worse.

An appropriate design uses the startup probe to allow the startup/restore phase to finish within a bounded time, the readiness probe to decide whether the Pod receives traffic, and the liveness probe to detect a process that genuinely cannot continue operating. The application must update health state according to the CRaC lifecycle; Kubernetes only observes probe results and takes the corresponding action.

## 1. Three Probes Answer Three Different Questions

| Probe | Question | On failure | Purpose |
|---|---|---|---|
| Startup | Has the application finished starting or restoring? | Kubelet restarts the container after reaching the failure threshold | Protects applications with slow startup/restore |
| Readiness | Can the container accept new requests right now? | Pod is not considered Ready and is removed from matching Service endpoints | Traffic control |
| Liveness | Is the process still in a state where it can continue serving or recover on its own? | Kubelet restarts the container after reaching the failure threshold | Detects deadlocks or unrecoverable process states |

Do not use the three probes interchangeably:

- The startup probe only governs the initial startup phase. Once the startup probe succeeds, the kubelet begins applying readiness and liveness probes.
- The readiness probe may fail temporarily multiple times without restarting the container. This is expected behavior when the application is waiting for a database or external service.
- A failing liveness probe can cause the kubelet to restart the container. Therefore, use it only for serious internal failures that a restart is likely to resolve.

Kubernetes evaluates probes based on HTTP, TCP, exec, or gRPC results depending on configuration. For HTTP probes, status codes in the range 200–399 are considered successful; other results, connection errors, or timeouts count as failures.

## 2. Why Must Probes Be Adjusted After CRaC Restore?

A checkpoint saves the state of a process at a point in time. While the process is not running, external systems continue operating. Upon restore, Java objects may be restored, yet the resources those objects represent have changed or expired.

For example:

- Database connections may have been closed by the server.
- Tokens or credentials may have expired.
- DNS records or service addresses may have changed.
- Distributed leases may have expired and been granted to another instance.
- Message consumers may need to create new sessions.
- Schedulers may have schedules that came due during the checkpoint interval.
- The HTTP server may not yet have opened its listener or completed warm-up.

Therefore, "JVM restored" does not equate to "application ready to accept traffic".

A typical sequence:

~~~text
Kubernetes starts container
          │
          ▼
JVM restores from checkpoint
          │
          ▼
CRaC afterRestore callbacks
          │
          ▼
Load runtime config and secrets
          │
          ▼
Reconnect database / broker / API
          │
          ▼
Verify dependencies and recover workers
          │
          ▼
Application completes bootstrap
          │
          ▼
Readiness switches to ACCEPTING_TRAFFIC
          │
          ▼
Kubernetes adds Pod to Service endpoints
~~~

While the steps above are taking place, readiness must return an unready status. Liveness should still succeed if the process is making normal progress. The startup probe tells the kubelet the maximum wait time allocated for the restore phase.

## 3. Startup Probe: Allowing Time for Startup and Restore

The startup probe is designed for containers with long startup times. When this probe is configured, Kubernetes does not run liveness and readiness probes until the startup probe succeeds.

This is useful when a Java application must perform post-restore steps:

1. Complete the CRaC restore lifecycle.
2. Load runtime configuration of the deployment environment.
3. Retrieve current secrets and credentials.
4. Recreate resources closed before checkpoint.
5. Recover frameworks, schedulers, or consumers.
6. Complete mandatory bootstrap steps.

### 3.1. Choosing the Startup Endpoint

Spring Boot Actuator provides health groups for liveness and readiness. Startup probe is a Kubernetes concept; the application can provide a dedicated endpoint, such as **/internal/startupz**, that returns success once the bootstrap/restore phase is complete.

The startup endpoint should return:

- **503 Service Unavailable** while the application is still restoring or bootstrapping.
- **200 OK** when startup/restore is complete and the application is ready to enter the readiness/liveness checking phase.

It is not always necessary to put every external dependency into the startup endpoint. If the database is temporarily unavailable while the application can still keep running and wait to reconnect, startup can complete while readiness continues failing. This separation avoids restarting the container merely because an external service is experiencing an outage.

If the application must connect to the database before completing bootstrap and cannot progress without the database, you may choose to include that step in the startup condition. Define a clear policy because failing the startup probe long enough causes the kubelet to restart the container.

### 3.2. Calculating Maximum Startup Time

Key fields:

- **periodSeconds**: interval between probe attempts.
- **timeoutSeconds**: maximum duration for a single probe.
- **failureThreshold**: number of consecutive failures before the probe is considered failed.

Example:

~~~yaml
startupProbe:
  httpGet:
    path: /internal/startupz
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 60
~~~

This configuration allows roughly a 5-minute wait window before the startup probe is considered failed. Actual time also depends on when probing starts, timeouts, and how the kubelet schedules probes.

Do not set failureThreshold too low if restore needs to load many resources. Nor should you set it too high to mask a permanent restore failure; monitor actual restore times and set a reasonable operational limit.

### 3.3. The Startup Probe Is Not a Second Readiness Probe

The startup probe only confirms the startup phase has passed a defined milestone. Once it succeeds, readiness continues governing traffic. For example, startup completes while the database cannot yet connect:

- Startup: succeeds.
- Liveness: succeeds if the process is still running.
- Readiness: fails because the application cannot yet serve requests needing the database.

This is a valid state. The container does not need to restart merely because it cannot accept traffic yet.

## 4. Readiness Probe: Accepting Traffic Only After Restore Completes

The readiness probe determines whether a container can accept new requests. When readiness fails, the Pod is not considered Ready and is normally removed from the Service endpoints used to send traffic to that Pod. The container keeps running; the kubelet does not restart it just because readiness fails.

This is the most important probe for protecting the application during the post-restore phase.

### 4.1. Readiness Conditions to Check

Post-restore readiness may depend on:

- CRaC callbacks have completed.
- Runtime configuration has been read and validated.
- Secrets/credentials have been retrieved.
- Database pools have been recreated and can issue valid connections.
- HTTP clients or broker clients have reconnected.
- Mandatory caches have been loaded.
- Resources needed for requests are operational.
- Mandatory workers or consumers have been recovered per policy.
- The application has opened its listener and can process requests.

Not every dependency has to be included in readiness. Include only dependencies truly required for serving requests. If an optional feature fails, the application can remain Ready provided endpoints depending on that feature are handled properly and the system has a clear degraded mode policy.

### 4.2. Readiness Should Not Cascade into Liveness Failure

For example, if the database is temporarily unreachable:

- Readiness should return failure if business requests obligatorily need the database.
- Liveness can still succeed because the JVM and web server remain operational and can reconnect when the database recovers.

If the same database health check is used for both readiness and liveness, a database outage can cause all Pods to restart simultaneously. When the database comes back, all Pods start up at once and create an additional connection burst.

### 4.3. Kubernetes Readiness Does Not Stop Background Jobs

Readiness primarily controls traffic through Services. It does not automatically stop:

- @Scheduled methods.
- @Async tasks.
- Message listeners.
- Dedicated worker threads.
- Retry loops or polling tasks.

If background workers must also wait for dependencies after restore, a separate admission gate or lifecycle coordinator is needed so work resumes only when resources are ready. Do not rely on the Pod not being Ready to prevent all types of background work.

## 5. Liveness Probe: Detecting an Unrecoverable Process

The liveness probe answers whether the process is still operating in a way that the application can continue serving.

Situations that can make liveness fail:

- The JVM is deadlocked in an essential component.
- The main event loop or a critical coordination thread is no longer making progress.
- The application entered an unrecoverable internal state.
- A critical error prevents the process from accepting or processing work any further.

Liveness should not check every external dependency. Databases, Redis, Kafka, or partner APIs may fail temporarily while the process remains alive and able to continue once the dependency recovers.

### 5.1. Do Not Use Liveness to Restart When the Database Disconnects

An incident-prone design:

~~~text
Liveness probe
     │
     ▼
HTTP check + database query
     │
     ▼
Database loses connection
     │
     ▼
Liveness fails on multiple Pods
     │
     ▼
Kubelet restarts containers
     │
     ▼
All pools recreate connections at once
     │
     ▼
Recovering database is overloaded
~~~

A better design:

~~~text
Liveness: check internal process
Readiness: check request capability, including mandatory dependencies
     │
     ├── Liveness OK, Readiness FAIL
     │       └── Container keeps running, Pod temporarily stops receiving traffic
     │
     └── Liveness FAIL
             └── Kubelet restarts container
~~~

Mark liveness BROKEN only when the process has no way to recover on its own. If an external dependency is failing, usually keep liveness CORRECT and readiness REFUSING_TRAFFIC.

## 6. Spring Boot Actuator and Kubernetes Health Groups

Spring Boot Actuator supports Kubernetes health groups:

- /actuator/health/liveness
- /actuator/health/readiness

The liveness group reflects LivenessState; the readiness group reflects ReadinessState. When running in a Kubernetes environment, Spring Boot can auto-configure these groups based on runtime conditions. They can be explicitly enabled for consistent behavior across local, test, and cluster environments.

Example application.yml:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

With add-additional-paths, Spring Boot can expose additional probe paths on the main HTTP port:

- /livez
- /readyz

This is useful when management endpoints run on a separate port. Probing on the main application port also checks the web server used by real requests, rather than only confirming the management server is alive.

If additional paths are not enabled, use Actuator endpoints on the exact port the application exposes. Check management.server.port, context path, and security rules to make sure the kubelet can reach them.

### 6.1. Customizing the Readiness Group

Default readiness reflects the application's readiness state. If the database is a mandatory dependency for every request, the database health indicator can be added to the group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
~~~

If the database is not needed for every request or degraded mode can be served, do not add it mechanically. One failing optional dependency does not have to remove the entire Pod from the Service.

Also avoid executing a heavy query on every probe. Health indicators should use short timeouts, lightweight operations, and not place significant load on a struggling system.

### 6.2. Notes on the Management Port

If Actuator is exposed on a separate port, probes hitting that port may succeed even when the main web server is down. Conversely, if the management port only binds to localhost, kubelet HTTP probes may fail to reach it as intended.

Choose one of two approaches:

1. Use /livez and /readyz on the main application port when the Spring Boot version supports additional paths.
2. Use /actuator/health/... on the management port and ensure that port is properly bound, exposed, and reachable from the kubelet.

Do not expose management endpoints to the Internet merely so Kubernetes can probe them. Keep health endpoints within internal network scope and apply appropriate security policies.

## 7. Updating Spring Boot Availability State in the CRaC Lifecycle

Spring Boot has an availability model with two key states:

- LivenessState.CORRECT and LivenessState.BROKEN.
- ReadinessState.ACCEPTING_TRAFFIC and ReadinessState.REFUSING_TRAFFIC.

The application can publish an AvailabilityChangeEvent to update states. Actuator's health groups read these states and return results to Kubernetes.

Example helper:

~~~java
package com.example.probes;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class ReadinessController {

    private final ApplicationEventPublisher publisher;

    public ReadinessController(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void refusingTraffic() {
        publisher.publishEvent(
                new AvailabilityChangeEvent<>(
                        this, ReadinessState.REFUSING_TRAFFIC));
    }

    public void acceptingTraffic() {
        publisher.publishEvent(
                new AvailabilityChangeEvent<>(
                        this, ReadinessState.ACCEPTING_TRAFFIC));
    }
}
~~~

Before checkpoint, the coordinator switches readiness to REFUSING_TRAFFIC before draining requests and background work. After restore, only switch to ACCEPTING_TRAFFIC after mandatory dependencies have been recovered.

Liveness should remain CORRECT during the restore phase as long as the process is still progressing and can complete on its own. If the application publishes BROKEN too early, the liveness probe may cause the kubelet to restart the container while callbacks are still performing recovery work.

## 8. Creating a Dedicated Startup Endpoint for the Restore Phase

Spring Boot does not have a default Kubernetes startup health group equivalent to liveness/readiness. A dedicated state can be created to represent the bootstrap process:

~~~java
package com.example.probes;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class RestoreStartupState {

    private final AtomicBoolean complete = new AtomicBoolean(false);

    public boolean isComplete() {
        return complete.get();
    }

    public void markInProgress() {
        complete.set(false);
    }

    public void markComplete() {
        complete.set(true);
    }
}
~~~

HTTP endpoint:

~~~java
package com.example.probes;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StartupProbeController {

    private final RestoreStartupState state;

    public StartupProbeController(RestoreStartupState state) {
        this.state = state;
    }

    @GetMapping("/internal/startupz")
    public ResponseEntity<Void> startup() {
        if (!state.isComplete()) {
            return ResponseEntity.status(503).build();
        }

        return ResponseEntity.ok().build();
    }
}
~~~

The endpoint must be lightweight and must not call databases or partner APIs on every kubelet probe. It only reads an in-memory state updated by the coordinator.

Ensure this state is reset to false at the start of every restore cycle. If a checkpoint is created while complete is still true, the snapshot may preserve that state and the startup probe will succeed too early. Before checkpoint, set startup state to false; after restore, set true only when restore bootstrap completes.

## 9. CRaC Coordinator Updating Readiness After Restore

A coordinator can manage resource recovery ordering and availability. The following sample illustrates coordination; RuntimeResources components must implement reconnection, validation, and cleanup logic suited to the application.

~~~java
package com.example.probes;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public class CracAvailabilityResource implements Resource {

    private final ReadinessController readiness;
    private final RestoreStartupState startupState;
    private final RuntimeResources runtimeResources;

    public CracAvailabilityResource(
            ReadinessController readiness,
            RestoreStartupState startupState,
            RuntimeResources runtimeResources) {

        this.readiness = readiness;
        this.startupState = startupState;
        this.runtimeResources = runtimeResources;

        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        readiness.refusingTraffic();
        startupState.markInProgress();

        runtimeResources.pauseBackgroundWork();
        runtimeResources.drainRequestsAndJobs();
        runtimeResources.closeResourcesForCheckpoint();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        readiness.refusingTraffic();
        startupState.markInProgress();

        try {
            runtimeResources.reloadRuntimeConfiguration();
            runtimeResources.reconnectDependencies();
            runtimeResources.validateRequiredResources();
            runtimeResources.resumeBackgroundWork();

            startupState.markComplete();
            readiness.acceptingTraffic();

        } catch (Exception failure) {
            readiness.refusingTraffic();
            throw failure;
        }
    }
}
~~~

Key points:

1. beforeCheckpoint marks the Pod as refusing traffic before stopping resources.
2. Startup state is reset so the checkpoint does not carry over completed bootstrap state from the previous run.
3. afterRestore keeps readiness refusing traffic throughout the entire recovery process.
4. Runtime config and secrets are loaded before creating dependent resources.
5. Background workers are resumed only when required dependencies are ready.
6. Readiness switches to ACCEPTING_TRAFFIC only in the final step.

The example is a skeleton illustrating sequence. If closeResourcesForCheckpoint() or a callback step fails, the application needs a specific recovery and logging policy. Do not swallow exceptions so Kubernetes sees a false healthy status.

### 9.1. Avoiding Two Components Owning the Same Resource

If HikariCP, HTTP clients, or message listeners already register their own CRaC Resources, the coordinator should not close/open the same resource a second time. Choose one lifecycle owner for each component and arrange registration order by dependency.

The readiness coordinator can orchestrate availability and the admission gate; dedicated resource owners take responsibility for the internal lifecycle of pools or clients. Ensure callbacks do not open traffic before those owners complete.

## 10. Configuring a Deployment with All Three Probes

Example Deployment using HTTP probes on the application's main port:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-service
  template:
    metadata:
      labels:
        app: orders-service
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example/orders-service:2.4.0
          ports:
            - name: http
              containerPort: 8080

          startupProbe:
            httpGet:
              path: /internal/startupz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 60

          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 1

          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

In the example:

- The startup probe gives the application up to roughly 5 minutes to complete restore bootstrap.
- Readiness is checked more frequently so the Pod quickly leaves the Service when unable to accept traffic and returns once ready.
- Liveness restarts the container only when the liveness endpoint fails consecutively per the configured threshold.
- terminationGracePeriodSeconds gives the application time to handle shutdown when the container is stopped.

These values are only starting points. Measure actual restore duration, database connection time, warm-up, and drain times to choose thresholds. If the startup probe fails enough times, the kubelet restarts the container; if the entrypoint always tries to restore the same broken checkpoint, the application may enter a restart loop. A strategy to fall back to cold start or discard invalid checkpoints is needed in the deployment process.

### 10.1. Using /actuator/health or /readyz?

If enabled:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

/livez and /readyz can be used as in the Deployment above.

If additional paths are not enabled, replace the paths with the corresponding Actuator endpoints, such as /actuator/health/liveness and /actuator/health/readiness, while pointing to the right management port. Do not assume a path and deploy without testing the actual endpoints.

## 11. Probe via HTTP, TCP, or Exec?

Kubernetes supports multiple probe types. Choose the type appropriate for the state to check.

| Type | Advantages | Limitations | When to use |
|---|---|---|---|
| HTTP GET | Can reflect application readiness/liveness logic | Requires web server and probe endpoints to work | Java web applications, Spring Boot Actuator |
| TCP socket | Checks whether a port accepts connections | Proves only that the port is open, not that dependencies or request paths work | Applications without HTTP health endpoints |
| Exec | Runs a command inside the container | Command can consume resources and spawn extra processes | Workers not exposing HTTP or needing local state checks |
| gRPC | Integrates with gRPC health protocol | Requires server supporting the health service and proper configuration | gRPC services |

A TCP probe only confirms a socket accepts connections. An HTTP server may open a port while application services are not yet ready; therefore, TCP does not replace readiness logic.

Exec probes should also not run heavy scripts or call numerous dependencies. Probes run periodically; each execution must be fast and have a clear timeout.

## 12. Designing Reliable Probe Endpoints

Probe endpoints are part of the control plane. If an endpoint is too heavy, unstable, or depends on the very component experiencing an outage, it can produce false negatives.

### 12.1. Respond Fast and With Timeouts

Endpoints should:

- Return results quickly without waiting indefinitely.
- Not perform migrations or warm-up inside a probe request.
- Not open new connections if only reading already-updated state.
- Not log stack traces on every failed probe.
- Not require complex authentication that the kubelet cannot provide.
- Not redirect to a login page.
- Have a timeout shorter than a reasonable probe period.

If checking the database is needed, use a health indicator with timeouts and rate limiting. A heavy query on every probe can further overload the database during recovery.

### 12.2. Do Not Expose Sensitive Information

Health responses should not return:

- JDBC URLs containing sensitive info.
- Usernames/passwords/tokens.
- Internal exception details.
- Unnecessary connection strings or topology.
- Customer business data.

Kubernetes only needs to know whether the probe succeeded or failed. Detailed logs should be kept in application logs/metrics with appropriate access controls.

### 12.3. Verify the Right Port and Context Path

If the application uses server.servlet.context-path, management.endpoints.web.base-path, or a separate management port, probe URLs must reflect the final path.

Check inside the container:

~~~bash
curl -i http://127.0.0.1:8080/internal/startupz
curl -i http://127.0.0.1:8080/readyz
curl -i http://127.0.0.1:8080/livez
~~~

This checks endpoints locally inside the container. Actual kubelet results also depend on port binding, network namespace, and Pod configuration.

## 13. Readiness During Checkpoint and When Checkpoint Fails

Readiness is not only important after restore; it also needs to be updated before taking a checkpoint.

A typical checkpoint workflow includes:

1. Mark REFUSING_TRAFFIC.
2. Stop accepting new requests and background work.
3. Drain running requests, transactions, and tasks.
4. Close resources needing recreation.
5. Request CRaC checkpoint.
6. After restore, recover dependencies and switch to ACCEPTING_TRAFFIC only when complete.

When readiness is false, the Service stops sending new traffic to the Pod per endpoint status. Running requests may still exist; readiness does not automatically drain active requests. The application must have its own graceful drain mechanism.

If checkpoint preparation fails before the process is dumped, the application needs to restore admission/readiness according to policy. For example, if drain times out and the callback rejects the checkpoint, the process may still keep running; reopen the gate and readiness if resources remain safe. If the dump succeeded and the process is restored, afterRestore is responsible for reopening readiness.

Do not assume the kubelet automatically infers checkpoint start or end from probes. Kubernetes only reacts to health endpoint results and container lifecycle reported by the runtime.

## 14. Background Workers and Consumers After Restore

Pod readiness does not automatically control schedulers or consumers. An application may not yet accept HTTP traffic while background workers keep processing.

If workers need recovered dependencies, the order should be:

~~~text
afterRestore
    │
    ▼
Load runtime config/secrets
    │
    ▼
Reconnect database / broker / API
    │
    ▼
Validate required resources
    │
    ▼
Resume scheduled jobs and consumers
    │
    ▼
Set readiness ACCEPTING_TRAFFIC
~~~

Some applications want to open HTTP traffic before resuming workers. That can make sense if workers do not affect request-serving capability. Decide based on your dependency graph and availability goals.

For message consumers, validate leases/sessions and offset state after restore. For @Scheduled, recalculate next-run times and missed-run policy. For multi-instance workers, use distributed locks, leases, or idempotency to avoid duplicate processing.

## 15. Liveness and Readiness in Multi-Replica Environments

Suppose a Deployment has three replicas. One replica restores slowly because the database connection is not yet ready:

- That replica returns readiness failure and does not yet receive traffic.
- The other two replicas continue serving.
- Liveness of the restoring replica still succeeds as long as the process is making progress.
- Once the database connection is confirmed and readiness succeeds, the replica is placed back into Service endpoints.

If liveness depends on the database, all three replicas can be restarted simultaneously when the database disconnects. When the database recovers, pools warm up together and create a connection burst. This is why readiness must be separated from liveness.

If all replicas restore at once, readiness keeps traffic away from instances until they are truly ready. Rollout strategies, maxUnavailable, maxSurge, startup budgets, and staggered restores can be used to avoid restarting total capacity simultaneously.

## 16. Distinguishing Restore Failures from Liveness Failures

Not every post-restore error should lead to the same action.

| Scenario | Startup | Readiness | Liveness | Action |
|---|---|---|---|---|
| Callback is recovering resources | Not yet succeeded | Fail | OK | Wait within startup budget |
| Database temporarily unavailable | Complete if bootstrap can wait independently | Fail if DB mandatory | OK | Keep container running, bounded retry |
| Optional partner API unavailable | Complete | Can be OK per degraded policy | OK | Keep dependent feature in limited state |
| Web server has not bound port | Fail or endpoint unreachable | Fail | Not probed yet until startup succeeds if startup probe exists | Wait within startup budget |
| Unrecoverable JVM/process deadlock | May have completed | Fail | Fail | Kubelet restarts container |
| Runtime config schema invalid | Fail if bootstrap cannot finish | Fail | Process may still be alive | Report error, do not open traffic; fix config |
| Checkpoint image incompatible | Restore process fails before endpoint opens | Fail | Unreachable | Fall back to cold start or ship compatible checkpoint |

This table assumes the startup endpoint represents bootstrap completion, readiness reflects mandatory dependencies, and liveness reflects only process health. Adjust to your actual architecture.

## 17. Observing and Diagnosing Probes After Restore

When a Pod is not Ready or is restarted, determine which probe triggered the action.

Useful commands:

~~~bash
kubectl describe pod <POD_NAME>
kubectl get pod <POD_NAME> -o wide
kubectl logs <POD_NAME> -c app --previous
kubectl logs <POD_NAME> -c app
~~~

The kubectl describe pod command displays Events and probe failure details. The --previous flag fetches logs of the previous container instance if the container has restarted and logs are still retained.

Log lifecycle milestones:

- restore_started
- runtime_config_loaded
- secrets_loaded
- database_reconnected
- external_clients_ready
- background_workers_resumed
- readiness_accepting_traffic

Metrics can be added:

| Metric | Meaning |
|---|---|
| crac_restore_duration_seconds | Time from when restore begins until bootstrap completes |
| crac_restore_failures_total | Number of failed restores |
| application_readiness | Traffic-accepting state |
| startup_probe_failures_total | Number of startup probe failures |
| readiness_probe_failures_total | Number of readiness probe failures |
| liveness_probe_failures_total | Number of liveness probe failures |
| background_active_tasks | Number of active background tasks |
| dependency_reconnect_duration_seconds | Time to reconnect dependencies |

Metric names are examples defined by the application/monitoring stack; Kubernetes does not automatically create all of these metrics.

Do not log secrets, tokens, or full health responses containing internal info. Clearly log the phase and component to distinguish whether restore is progressing, a dependency is retrying, or the process is genuinely hung.

## 18. Common Configuration Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| No startup probe for lengthy restores | Liveness may restart container prematurely | Use a startup probe with a budget measured from real restores |
| Startup probe checks database while DB is only temporarily unavailable | Container restarts even though process can wait | Separate startup completion from readiness dependencies |
| Readiness always returns 200 after restore | Pod receives traffic before pools/clients are ready | Keep REFUSING_TRAFFIC until resources are valid |
| Liveness runs database query | Database outage triggers mass restarts | Keep liveness independent of external dependencies |
| Probe uses wrong port/context path | Kubelet repeatedly reports failures | Verify actual endpoints inside the container |
| Management port alive while main server dead | Probe gives false healthy result | Use additional paths on main port or check the web server too |
| Readiness used to stop schedulers | Background jobs keep running | Use a separate admission gate for workers |
| Startup flag checkpointed in true state | Startup probe succeeds before restore finishes | Reset startup state before checkpoint and set complete only after restore |
| Threshold too low | Valid restores get restarted | Measure p95/p99 restore duration and increase budget reasonably |
| Threshold too high | Prolonged restore failures detected slowly | Set finite timeouts, alerts, and fallback |
| Liveness fails then repeatedly restores the same broken checkpoint | Container restart loop | Have a cold-start/fallback strategy and invalid checkpoint management |

## 19. Testing Probes with CRaC

Test both happy paths and failure paths on the exact Kubernetes, container runtime, CRaC JDK, CRIU, and Spring Boot versions to be deployed.

### 19.1. Happy Path

1. Create a checkpoint in the preparation environment.
2. Ensure readiness is switched to REFUSING_TRAFFIC before checkpoint.
3. Start the Pod from the checkpoint.
4. Confirm the startup probe fails while restore is not yet finished.
5. Confirm liveness/readiness are not used before the startup probe succeeds.
6. Observe post-restore callbacks loading config and reconnecting dependencies.
7. Confirm the startup endpoint transitions to success.
8. Confirm readiness transitions to success only after mandatory health checks.
9. Send requests through the Service and confirm the Pod receives traffic only when Ready.

### 19.2. Database Unavailable

1. Restore the Pod while the database is temporarily unreachable.
2. Allow bootstrap to finish if the application can continue waiting for the dependency.
3. Confirm readiness fails.
4. Confirm liveness still succeeds.
5. Restore the database.
6. Confirm the application reconnects and readiness transitions to success without restarting the container.

If the application cannot complete startup without the database, verify the startup budget and decide on intentional restart/fallback.

### 19.3. Hung Process

In a test environment, induce a genuinely unrecoverable liveness condition, such as making the main coordination component stop making progress. Confirm liveness fails consecutively and the kubelet restarts the container per policy.

Do not use a database outage to simulate a process deadlock, because the two scenarios require different actions.

### 19.4. Restore Failure

Test an incompatible checkpoint or missing runtime resources in staging. Confirm:

- The startup probe does not report a false success.
- Readiness does not switch to ACCEPTING_TRAFFIC.
- Logs indicate the failed restore phase.
- The kubelet takes the right action per threshold.
- The Deployment has an appropriate fallback instead of looping endlessly with a broken checkpoint.

### 19.5. Checking Service Endpoints

Pod readiness and EndpointSlice can be observed:

~~~bash
kubectl get pods -l app=orders-service
kubectl get endpointslices -l kubernetes.io/service-name=orders-service
~~~

When readiness fails, confirm the Pod is not considered a Ready endpoint for the Service to send new traffic. After readiness succeeds, endpoints are updated according to the Pod's status.

## 20. Recommended Deployment Flow

A clear operational workflow can be structured as follows:

~~~text
CHECKPOINT PREPARATION
  - Mark readiness REFUSING_TRAFFIC
  - Pause background job/consumer admission
  - Drain active requests and tasks
  - Close resources needing recreation
  - Take checkpoint
          │
          ▼
CONTAINER START / RESTORE
  - Launch from checkpoint
  - Startup probe waits for restore bootstrap
          │
          ▼
AFTER RESTORE
  - Reset/keep startup state incomplete
  - Load runtime config and secrets
  - Reconnect dependencies
  - Validate resources
  - Resume workers per policy
          │
          ▼
PROBE STATES
  - Startup: success
  - Liveness: process healthy
  - Readiness: accepting traffic
          │
          ▼
KUBERNETES SERVICE
  - Pod is considered Ready
  - Service can send new traffic
~~~

Configuration should be versioned together with the deployment. When changing endpoints, health groups, or startup duration, re-test the entire restore process rather than testing only application cold start.

## 21. Principles to Remember

Startup, readiness, and liveness have distinct roles. After CRaC restore, the startup probe protects recovery time; readiness keeps traffic away from the Pod until mandatory resources and dependencies are operational; liveness requests a restart only when the process genuinely cannot continue.

Spring Boot Actuator provides liveness/readiness health groups and availability states for the application to control probe outcomes. CRaC callbacks should keep readiness at REFUSING_TRAFFIC throughout recovery, reset startup completion before checkpoint, and publish readiness only after required configuration, secrets, connection pools, clients, and workers have been restored.

Kubernetes does not understand the meaning of checkpoint images or CRaC callbacks. It only sees probe outcomes and container status. When endpoints accurately reflect the lifecycle, the kubelet can wait for restore, avoid sending traffic too early, and restart the process only when there is evidence of a genuine liveness failure.

## 22. References

- [Kubernetes: Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): semantics, configuration, and behavior of the three probes.
- [Spring Boot: Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): liveness/readiness health groups and Actuator endpoints.
- [Spring Boot: Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html): liveness/readiness states and availability events.
- [CRaC: Implementing the CRaC API](https://crac.org/use/implement-crac/): resource management before checkpoint and after restore.

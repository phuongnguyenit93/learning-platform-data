# Comparing Graceful Application Shutdown with Forced Process Termination

In microservices, how a provider stops running directly impacts service discovery. When an application shuts down gracefully, it gets a chance to announce it is stopping traffic intake, deregister from the registry, complete in-flight requests, and close resources in order. When a process is forcefully terminated, shutdown hooks may not run; the registry only notices the instance is gone after a failed health check, lease expiration, or session expiration.

These two ways of stopping produce different behaviors in the provider, Eureka/Consul/ZooKeeper, the consumer's discovery cache, and in-flight requests. This practice compares both scenarios, configures Spring Boot graceful shutdown, inspects termination flows in Docker/Kubernetes, and measures the time until the instance stops being selected.

## 1. Objectives and Practice Context

Suppose we have a system consisting of:

- Eureka Server or Consul as the registry.
- Two replicas of the `inventory-service` service.
- One consumer `order-service` calling `inventory-service` by service ID.
- An endpoint that takes around 10 seconds to process a request so we can observe in-flight requests.

We will stop one replica in two ways:

1. **Graceful shutdown:** send a handleable termination signal so the application stops accepting new requests, withdraws from discovery, and completes in-flight requests within a time limit.
2. **Forced termination:** end the process immediately without waiting for Spring to close the context or complete requests.

The objective is not merely seeing that the process has stopped. You must verify:

- At what point the consumer stops selecting the instance.
- Whether in-flight requests complete or get interrupted.
- How the registry removes or marks the instance.
- Whether the remaining replica continues serving.
- Whether a new instance can re-register after starting up.

## 2. Where Do the Two Shutdown Approaches Differ?

| Criterion | Graceful Shutdown | Forced Termination |
|---|---|---|
| Typical signal | SIGTERM or stop command with timeout | SIGKILL, kill -9, or force kill |
| JVM shutdown hooks | Have a chance to run | Do not run |
| Spring ApplicationContext | Has a chance to close per lifecycle | No chance for normal closure |
| In-flight requests | Can be drained within timeout | May be interrupted immediately |
| Deregistration | Has a chance to execute via lifecycle/client | Cannot rely on shutdown hooks |
| Resources | Can flush, close pools and files | Reclaimed by OS on process death; unflushed data may be lost |
| Registry cleanup | Can be proactive; still needs propagation | Usually relies on leases, health checks, or sessions |
| Predictability | Higher if timeouts are properly configured | Depends on timing and failure detection mechanisms |

SIGTERM does not automatically guarantee graceful shutdown. The application must handle the signal and have an appropriate shutdown procedure; if waiting exceeds the limit of Docker, Kubernetes, or systemd, the process may eventually still receive SIGKILL.

Conversely, SIGKILL ends the process without invoking shutdown hooks. No `@PreDestroy`, `DisposableBean.destroy()`, or lifecycle callback code can run after the process has received SIGKILL.

## 3. Graceful Shutdown Flow of a Provider

A controlled shutdown procedure typically consists of these steps:

1. Receive the stop request and transition readiness status to refuse new traffic.
2. Inform routing systems and consumers that the instance is about to leave the service.
3. Deregister from the registry or let the registry client do so during shutdown lifecycle.
4. Stop accepting new requests at the web server.
5. Wait for in-flight requests to finish within the timeout limit.
6. Close connection pools, schedulers, message listeners, and remaining resources.
7. Exit the JVM.

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as Spring Boot app
    participant R as Service registry
    participant C as Consumer
    O->>A: SIGTERM / stop request
    A->>A: Readiness = REFUSING_TRAFFIC
    A->>R: Deregister or update status
    R-->>C: Registry changes
    C->>R: Refresh / receive changes
    A->>A: Stop accepting new requests
    A->>A: Drain in-flight requests
    A->>A: Close beans and resources
    A-->>O: Process exit
~~~

The exact ordering among deregistration, readiness, and web server shutdown depends on the registry client, web server, and Spring Boot/Spring Cloud version. The critical point is not to close listeners or connections still needed by in-flight requests before draining finishes. Test your application's actual lifecycle rather than assuming enabling a single property fixes the entire chain.

### Readiness vs. Liveness

- **Liveness** answers whether the process needs to be restarted.
- **Readiness** answers whether the instance should receive new traffic.

When shutdown begins, the instance may still be alive and finishing requests, while readiness must transition to unready. Do not use liveness to represent draining state; if liveness fails, Kubernetes may restart the container while it is shutting down.

## 4. Configuring Graceful Shutdown in Spring Boot

With Spring Boot supporting graceful shutdown for embedded web servers, you can configure:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Meaning:

- `server.shutdown: graceful` instructs the embedded web server to stop accepting new connections/requests according to the server's graceful mechanism.
- `spring.lifecycle.timeout-per-shutdown-phase` sets the maximum wait time for each lifecycle phase while closing the context.
- Health probes allow the platform to inspect readiness/liveness via Actuator if the endpoints are properly configured and exposed.

A 30-second timeout is only an example. Choose based on the longest allowed request processing time, drain duration, resource closing tasks, and the orchestrator's grace period. Too short a value can cut off requests; too long a value can prolong rollouts or scale-downs.

Different web servers and Spring Boot versions may vary in how they handle open connections, HTTP/2, streaming responses, and async requests. Check documentation for your exact version and measure with an actual in-flight request.

### Checking the Readiness Endpoint

With Actuator probes, the readiness endpoint typically has the form:

~~~text
/actuator/health/readiness
~~~

In Kubernetes, point the readiness probe to this endpoint. When the application starts shutting down, Spring Boot can transition readiness state to `REFUSING_TRAFFIC` during its lifecycle. If you need to transition earlier to allow propagation time to load balancers/registries, the application can implement a separate pre-drain step and publish the readiness state before closing the context.

Do not expose all Actuator endpoints to the public network. Only expose necessary endpoints on the management network and protect them with appropriate policies.

## 5. Deregistering from the Service Registry

Stopping the web server and deregistering are two different actions:

- The web server stops accepting direct requests.
- The registry stops supplying the instance to new consumers.

With Spring Cloud, the registry client typically participates in the application context lifecycle. When the context closes normally, the implementation can deregister or close the corresponding registration/session. Exact behavior depends on the provider and version.

If the application registers manually using `ServiceRegistry`, proactively invoke deregistration in the right lifecycle phase. Do not invoke manual deregistration redundantly alongside automatic mechanisms without understanding provider semantics; duplicate or mismatched operations can cause unexpected state.

### Eureka

Eureka Client normally registers the instance, sends periodic renewals, and can send a cancellation when the client closes cleanly. When a process receives SIGKILL, cancellation is not sent; the server can only detect that the instance stopped renewing after lease expiration and eviction.

If Eureka has self-preservation enabled, eviction may be throttled when renewals are abnormally low. Thus, a killed process can stay in the registry longer than the expected lease duration. Consumers may continue receiving the stale instance until the registry and caches converge.

### Consul

With Spring Cloud Consul, the client can deregister the service when the application closes according to the integration lifecycle. If the agent health check stops passing, the catalog can mark the instance critical; the policy for deregistering critical services and retention duration depend on Consul agent configuration.

When a process is killed, the Consul agent can detect it via health check or TTL check. This does not coincide with process exit. Check both check status on the agent and on the catalog server.

### ZooKeeper

Registrations can be represented by ephemeral znodes tied to a session. When the client closes the session cleanly, the ephemeral node is deleted. When a process is killed or loses network connectivity, the node normally disappears only once ZooKeeper determines the session has expired.

Therefore, a force kill does not make the ephemeral node vanish immediately. Session timeout and reconnect behavior affect when consumers stop seeing the registration.

## 6. What Problems Does Force Kill Expose?

When a process terminates abruptly:

- The JVM does not run shutdown hooks.
- Spring does not invoke context closing callbacks.
- The registry client has no chance to send deregistration/cancellation.
- In-flight requests may be reset or lose their responses.
- Uncommitted transactions or unflushed data may be left in an inconsistent state.
- Consumers can still pick the old instance from the registry/cache.
- The registry only updates after health check failure, lease expiration, or session expiration.

A request already sent to an instance before force kill can fail even if the consumer has obtained a fresh instance list. Discovery cannot move an already running request back from a dead process. Retrying is only safe when operations are idempotent or protected against duplicate processing.

## 7. Practicing with Docker

Suppose a container named `inventory-service` is running and registered in Eureka or Consul.

### Graceful Shutdown

~~~bash
docker stop --time 40 inventory-service
~~~

Docker sends the stop signal (usually SIGTERM, unless the image configures a different `STOPSIGNAL`), waits up to 40 seconds, and then force kills if the process has not exited.

### Forced Termination

~~~bash
docker kill --signal KILL inventory-service
~~~

This command sends SIGKILL immediately. The container has no opportunity to perform graceful shutdown.

### Observation

~~~bash
docker inspect inventory-service
docker logs --timestamps inventory-service
~~~

Record the stop/kill timestamp, shutdown logs, exit code, and container status. Then inspect the instance in the registry and call the consumer continuously to determine:

- When the registry removes or marks the instance.
- When the consumer stops choosing that endpoint.
- Whether any requests were reset during shutdown.

Run these commands only on containers in your lab environment. Never use generic container names or bulk stop commands in shared environments.

### PID 1 and Shell Wrappers

If a container launches the application through a shell script, the shell must forward signals to the Java process. Use `exec` so Java replaces the shell process:

~~~dockerfile
ENTRYPOINT ["sh", "-c", "exec java -jar /app/application.jar"]
~~~

If the shell remains PID 1 and does not forward signals, Docker may send SIGTERM to the shell while the JVM never properly receives it. Then `docker stop` may wait out the timeout before sending SIGKILL, turning an apparently graceful setup into a forced stop.

## 8. Practicing with Kubernetes

When a Pod is deleted or replaced, Kubernetes performs termination in a sequence. At a high level:

1. The Pod is marked Terminating.
2. EndpointSlice and routing components update endpoint status; propagation has latency.
3. The `preStop` hook runs if configured.
4. Kubelet sends the termination signal (usually SIGTERM) to the container.
5. The application has time to shut down within `terminationGracePeriodSeconds`.
6. Once the grace period expires, surviving processes may receive SIGKILL.

The grace period starts before `preStop` runs. Time used by the hook counts toward the total termination budget; hook time is not added on top of `terminationGracePeriodSeconds`.

Deployment example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inventory-service
  template:
    metadata:
      labels:
        app: inventory-service
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: inventory
          image: inventory-service:latest
          ports:
            - name: http
              containerPort: 8080
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
~~~

This example budgets 5 seconds for preStop, 30 seconds for Spring lifecycle shutdown, and the remainder as margin. This is only an illustration of the budget; `sleep` alone neither fails readiness nor deregisters from Eureka/Consul. In production, replace it with an intentional pre-drain hook or endpoint if time is needed for routing and registry propagation.

In real deployments:

- Set `terminationGracePeriodSeconds` larger than the total preStop, drain, and shutdown time required, plus margin.
- Ensure readiness reflects the impending shutdown state.
- Use suitable `maxUnavailable` and `maxSurge` so rollouts do not wipe out all replicas.
- Do not let liveness probes restart the application just because readiness is REFUSING_TRAFFIC.
- Inspect EndpointSlice, registry, and request path; they may update at different times.

### Example Time Budget

| Phase | Illustrative Budget |
|---|---:|
| Propagation/preStop | 5 seconds |
| Drain and Spring lifecycle shutdown | 30 seconds |
| Margin | 10 seconds |
| Total grace period | 45 seconds |

Not all steps run strictly sequentially. Measure actual durations to choose the grace period; streaming or async requests may require dedicated policies.

## 9. Taking Control of Shutdown Ordering

If the application needs to proactively switch readiness before Spring starts closing the web server, it can publish the `REFUSING_TRAFFIC` state from a controlled pre-drain step.

Example simple component to change state:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class ReadinessControl {

    private final ConfigurableApplicationContext context;

    public ReadinessControl(ConfigurableApplicationContext context) {
        this.context = context;
    }

    public void refuseNewTraffic() {
        AvailabilityChangeEvent.publish(
            context,
            ReadinessState.REFUSING_TRAFFIC
        );
    }
}
~~~

This is a building block, not a complete shutdown coordinator. Call `refuseNewTraffic()` from a pre-drain mechanism aligned with your orchestrator or application lifecycle, then wait for propagation time before beginning server shutdown.

Do not call `context.close()` immediately inside an uncontrolled callback while requests are still running. Also do not deregister before readiness/routing has had a chance to update if the architecture relies on a drain window. Optimal ordering depends on whether consumers route through a Kubernetes Service, Eureka, Consul, or multiple layers simultaneously.

With manual registration, `ServiceRegistry.deregister(registration)` can be called from a lifecycle component. However, if the Eureka/Consul starter already manages registration automatically, inspect the existing lifecycle before adding manual deregistration to avoid calling it twice or using the wrong registration.

## 10. Test Comparing the Two Shutdown Approaches

Preparation:

- Two `inventory-service` replicas.
- A consumer continuously calling by service ID.
- A test endpoint taking 10 seconds to process and returning the instance ID.
- Logs or metrics recording request start/finish.
- Registry dashboard/API to observe registrations.

Run the same scenario twice, changing only how the provider is stopped.

### Scenario A — Graceful Shutdown

1. Confirm both instances are healthy and the consumer can call both.
2. Send a 10-second request to instance A.
3. While the request is in flight, send SIGTERM or run `docker stop` with a sufficiently long timeout.
4. Record when readiness switches to refusing traffic.
5. Record when the instance is deregistered or stops being returned by the registry.
6. Record when the in-flight request completes.
7. Confirm the consumer only selects instance B for new requests.

### Scenario B — Forced Termination

1. Restore both instances and confirm the baseline.
2. Send a 10-second request to instance A.
3. While the request is in flight, send SIGKILL or force kill the container.
4. Record when the request resets or times out.
5. Monitor health checks, leases, or sessions until the registry updates.
6. Confirm the consumer stops selecting A and switches to B.
7. Record how long the stale endpoint remains present in the registry/cache.

### Results Table

| Metric | Graceful | Force kill |
|---|---:|---:|
| Time from stop signal to process exit | Measure actual | Measure actual |
| In-flight request completed | Yes/No | Yes/No |
| Proactive deregistration | Yes/No | Not expected |
| Time for registry to remove instance | Measure actual | Measure actual |
| Time for consumer to stop selecting instance | Measure actual | Measure actual |
| Failed requests during stop window | Count | Count |
| Healthy instances impacted | Count | Count |

Do not fill hypothetical numbers into the table. Run the experiment and extract timestamps from logs, traces, registry, and consumer.

## 11. Interpreting the Results

A good graceful shutdown result typically shows:

- Readiness transitions to refusing new traffic.
- New requests are routed to the remaining healthy replica.
- In-flight requests complete within the timeout.
- The registry deregisters or updates health status quickly.
- Consumer caches converge and stop choosing the stopped instance.

A force kill result typically shows:

- No shutdown hook or proactive deregistration.
- In-flight requests may fail.
- The registry retains the instance until health/lease/session detection triggers.
- Consumers may call the old endpoint during the stale window.

If graceful shutdown still leaves consumers calling the stopped instance for a long time, check:

1. Did readiness actually switch to REFUSING_TRAFFIC?
2. Did the registry client deregister when the context closed?
3. What registry or private cache does the consumer use?
4. Does LoadBalancer cache the instance list?
5. Is there a proxy or gateway caching DNS/endpoints?
6. Was the shutdown timeout long enough to drain?

If force kill does not cause a request failure, the request may have been handled by the other replica or the test did not guarantee the request was running on the killed instance. Verify the request's instance ID before drawing conclusions.

## 12. Common Issues

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `docker stop` always waits until timeout | Java does not receive SIGTERM, shell does not forward signal, or shutdown hangs | Check PID 1, exec, shutdown logs, and lifecycle phases |
| Pod receives SIGKILL despite graceful config | Grace period is shorter than combined preStop and drain time | Measure each phase and increase budget accordingly |
| Readiness stays UP when shutdown begins | Probe does not reflect refusing traffic state | Check Actuator readiness and pre-drain logic |
| Registry retains instance after graceful shutdown | Registry lifecycle did not deregister or operation failed | Check client shutdown logs and REST/catalog state |
| Registry retains instance after force kill | Lease, health check, or session has not expired | Check registry semantics and timeouts |
| In-flight request lost during graceful shutdown | Web server closes immediately, timeout too short, or async task incomplete | Check server shutdown mode, phase timeout, and request duration |
| Consumer still picks instance after deregister | Fetch interval/cache or propagation delay | Check DiscoveryClient and LoadBalancer selection |
| Kubernetes rollout causes downtime | Inappropriate maxUnavailable, readiness, or replica count | Check Deployment strategy and EndpointSlice |
| Shutdown hooks do not run in container | PID 1/shell wrapper or force kill | Check entrypoint and stop signal |

## 13. Design and Operational Principles

- Use graceful shutdown for rollouts, scale-downs, and controlled stops.
- Treat SIGTERM as the start of the shutdown lifecycle, not proof that the application has finished draining.
- Use SIGKILL only when forced termination is needed or after the grace period expires.
- Transition readiness to refusing traffic before stopping new request acceptance.
- Deregister from the registry in the lifecycle phase matching the implementation.
- Wait for in-flight requests within a bounded timeout.
- Set Spring's shutdown timeout smaller than the orchestrator's grace period, leaving margin.
- Ensure container PID 1 forwards signals to the JVM.
- In Kubernetes, account for preStop time within terminationGracePeriodSeconds.
- Measure the stale window at both registry and consumer, not just process status.
- Design safe retries with idempotency; discovery cannot rescue an already aborted request.
- Test both graceful and forced termination in staging before choosing production timeouts.

Graceful application shutdown gives the provider an opportunity to step out of traffic and finish ongoing work; forced termination kills the process before those lifecycle steps happen. The registry and consumer have separate detection mechanisms, so process exit, registration removal, and request recovery times do not align. Comparing via an experiment with an active request, recording timestamps across provider/registry/consumer, and verifying the remaining replica helps choose the right shutdown timeouts and recovery policies for a Spring Cloud Service Discovery system.

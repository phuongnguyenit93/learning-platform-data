# Draining Traffic, Waiting for In-Flight Requests, and Graceful Shutdown

When deploying a new version, performing maintenance, or replacing a microservice instance, simply sending a process-stop command is not enough. Consumers may still see the instance in the registry and keep sending requests to it; in-flight requests may be cut off mid-flight; message consumers or background tasks may lose unfinished work.

A safe shutdown procedure must follow an order: remove the instance from the traffic-receiving path, wait for that status to propagate to the registry and routers, stop accepting new work, wait for in-flight work to finish within a time limit, and only then close the ApplicationContext and exit the process. Spring Boot supports graceful shutdown for embedded web servers; Spring Cloud and registries provide mechanisms to mark or deregister an instance; the deployment platform must grant enough time for the entire sequence.

## 1. Three Distinct Actions During Service Shutdown

Three goals must be distinguished:

| Goal | Action Required | Desired Outcome |
|---|---|---|
| Traffic drain | Mark the instance as not accepting new requests in the registry, readiness, or load balancer | Consumers stop selecting that instance |
| In-flight drain | Stop accepting new requests/jobs and wait for current requests and tasks to complete | Ongoing processing is not interrupted |
| Graceful shutdown | Send SIGTERM, shut down the server and beans per lifecycle with a timeout | Resources are released in an orderly manner |

These three actions are related but do not replace one another. Marking `OUT_OF_SERVICE` does not wait for current requests to finish. Web server graceful shutdown does not guarantee the registry has stopped advertising the instance. Deregistering only removes the registration; it does not stop the process or complete background work.

## 2. Overall Shutdown Sequence

A rolling deployment workflow can proceed as follows:

    New deployment
          |
          v
    Start new instance
          |
          v
    New instance health/readiness passes
          |
          v
    Mark old instance not accepting traffic
          |
          v
    Registry and LoadBalancer update list
          |
          v
    Stop accepting new requests and work
          |
          v
    Wait for in-flight requests/jobs to complete
          |
          v
    Send SIGTERM to old instance
          |
          v
    Spring Boot graceful shutdown
          |
          v
    Deregister and release resources
          |
          v
    Process exits

In a rolling deployment, ensure the new instance is ready before draining the old one. If you remove the old instance before replacement capacity is available, the system may lack serving capacity while the registry updates.

After marking an instance as not accepting traffic, wait for the registry, `DiscoveryClient` caches, `LoadBalancer` caches, and relevant proxies to update. There is no fixed wait duration applicable to all systems. Observe registry state and real consumer traffic.

## 3. Readiness Differs from Liveness and Overall Health

Spring Boot has two important availability states:

- Liveness indicates whether the process is in a state where it can continue operating or needs to be restarted.
- Readiness indicates whether the application is ready to receive new traffic.

When draining begins, the application should transition readiness to `REFUSING_TRAFFIC`. Liveness can remain `CORRECT` because the process is still healthy and needs time to finish current requests.

Health probes can be enabled in `application.yml`:

    management:
      endpoint:
        health:
          probes:
            enabled: true
      endpoints:
        web:
          exposure:
            include: health,info

Spring Boot provides the endpoints:

    /actuator/health/liveness
    /actuator/health/readiness

The readiness probe must be consumed by the load balancer or deployment platform. Exposing the readiness endpoint alone does not automatically cause Eureka, Consul, or an arbitrary proxy to stop sending traffic. Integrate the probe with the corresponding routing component.

## 4. Proactively Transitioning Readiness to REFUSING_TRAFFIC

Spring Boot allows changing readiness state via `AvailabilityChangeEvent`. You can build an internal administrative endpoint to initiate draining:

    import org.springframework.boot.availability.AvailabilityChangeEvent;
    import org.springframework.boot.availability.ReadinessState;
    import org.springframework.context.ApplicationEventPublisher;
    import org.springframework.http.ResponseEntity;
    import org.springframework.web.bind.annotation.PostMapping;
    import org.springframework.web.bind.annotation.RequestMapping;
    import org.springframework.web.bind.annotation.RestController;

    @RestController
    @RequestMapping("/internal/lifecycle")
    public class LifecycleController {

        private final ApplicationEventPublisher publisher;

        public LifecycleController(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        @PostMapping("/drain")
        public ResponseEntity<Void> drain() {
            AvailabilityChangeEvent.publish(
                    publisher,
                    this,
                    ReadinessState.REFUSING_TRAFFIC
            );
            return ResponseEntity.accepted().build();
        }
    }

After calling this endpoint, the readiness health group reflects the traffic-refusing state. Monitoring components can observe readiness transition to `OUT_OF_SERVICE` or `DOWN` depending on how health status is mapped.

The drain endpoint must be protected with authentication, authorization, and network access restrictions. Do not expose this administrative endpoint publicly. Design the operation to be idempotent so repeated calls do not break the lifecycle.

Transitioning readiness affects only components that actually check readiness. If consumers call directly via Eureka or Consul, update registry status or configure appropriate health integration.

## 5. Removing an Instance from the Registry

### Eureka

Eureka supports the `OUT_OF_SERVICE` status. The instance keeps its registration but is not returned as an active instance in normal discovery queries.

Spring Cloud Commons provides the Service Registry Actuator endpoint. You can expose it in `application.yml`:

    management:
      endpoints:
        web:
          exposure:
            include: health,info,serviceregistry

Read current status:

    curl http://localhost:8080/actuator/serviceregistry

Take the instance out of traffic:

    curl -X POST http://localhost:8080/actuator/serviceregistry \
      -H "Content-Type: application/json" \
      -d "{\"status\":\"OUT_OF_SERVICE\"}"

After draining and maintenance finish, restore `UP` status if the instance is still running:

    curl -X POST http://localhost:8080/actuator/serviceregistry \
      -H "Content-Type: application/json" \
      -d "{\"status\":\"UP\"}"

Valid status values depend on the `ServiceRegistry` implementation and Spring Cloud version. With Eureka, `OUT_OF_SERVICE` is a supported status. Read the status back with GET and verify the instance list received by consumers.

Spring Cloud Netflix also supports actuator pause/resume. When these endpoints are enabled, calling `/actuator/pause` puts the Eureka instance into `OUT_OF_SERVICE`; `/actuator/resume` removes the override so the instance returns to the status reported by the application after the next heartbeat. Check endpoint exposure and security settings before using them.

### Consul

Consul can place a service into maintenance mode by `ServiceID`. When maintenance is enabled, the service is marked unavailable and excluded from relevant DNS/API results.

Agent API:

    curl -X PUT \
      "http://localhost:8500/v1/agent/service/maintenance/inventory-service-8080?enable=true&reason=planned-drain"

When bringing the service back:

    curl -X PUT \
      "http://localhost:8500/v1/agent/service/maintenance/inventory-service-8080?enable=false"

Replace `inventory-service-8080` with the actual `ServiceID`. The Agent API requires the `service:write` ACL permission. Do not confuse the instance's `ServiceID` with the service name used for querying.

If consumers use Spring Cloud Consul, you can enable `query-passing` to receive only instances with passing health checks:

    spring:
      cloud:
        consul:
          discovery:
            query-passing: true

Maintenance mode and health checks are two separate signals. Maintenance actively pulls the service out of the pool; health checks reflect endpoint check results. Verify status in Consul and service health query results before stopping the process.

### Difference Between OUT_OF_SERVICE and Deregister

`OUT_OF_SERVICE` or maintenance keeps the registration while marking that the service should not receive traffic. Deregister deletes the registration from the registry. In a maintenance flow where an instance will be restarted, you can use out-of-service first and let the lifecycle deregister when the application closes. If the instance will keep running after maintenance, bring it back to `UP` or disable maintenance mode after readiness passes.

## 6. Waiting for the Registry and Consumers to Stop Sending Requests

After updating status, do not stop the process immediately. Wait for the new status to reach all components that can select instances:

- The registry server or Consul Catalog receives the change.
- Consumers' Eureka clients or Consul Discovery clients refresh their lists.
- Spring Cloud LoadBalancer caches refresh.
- Gateways, reverse proxies, or service meshes update endpoint pools.
- Consumers no longer select the old instance for new requests.

Latency depends on heartbeats, registry fetch intervals, response caches, health-check intervals, client caches, and load balancer settings. Persistent connections or keep-alive can also allow requests to keep flowing over an already-established connection.

The best verification is to observe actual traffic and instance lists from the consumer side. Use per-instance request metrics, access logs, a load balancer dashboard, or a discovery inspection endpoint. Simply waiting an arbitrary number of seconds without verification can allow new requests to continue hitting a stopping instance.

If the system has multiple cache layers, identify which layer governs instance selection and its refresh interval. Consumer retries must also be accounted for because a request may be retried against another instance after an initial failure.

## 7. Waiting for In-Flight HTTP Requests to Complete

Once the instance stops receiving new traffic, give current requests time to finish. Spring Boot graceful shutdown supports embedded web servers in both Servlet and Reactive applications.

Configure explicitly in `application.yml`:

    server:
      shutdown: graceful

    spring:
      lifecycle:
        timeout-per-shutdown-phase: 45s

When `ApplicationContext` begins closing, Spring Boot initiates graceful shutdown during the `SmartLifecycle` stop phase. The web server stops accepting new requests according to the server's implementation and waits for in-flight requests to complete within the grace period.

With Tomcat, Jetty, and Reactor Netty, the server stops accepting new requests at the network layer during graceful shutdown. Exact handling of new connections can vary by server and version. Undertow in supported versions may still accept connections while returning HTTP 503 during the shutdown phase.

`spring.lifecycle.timeout-per-shutdown-phase` is the time limit for each lifecycle shutdown phase. If requests have not completed when time runs out, shutdown continues and remaining work may be interrupted. Therefore, the timeout must exceed normal request processing time and fit within the platform's termination limit.

In current Spring Boot versions, graceful shutdown is enabled by default for supported embedded web servers. Explicitly declaring `server.shutdown=graceful` makes configuration intent clear and should be verified against the specific Boot version and server in use.

## 8. Choosing Timeouts Based on Actual Processing Duration

Do not set timeouts too short just to speed up rollouts. If normal requests can take 20 seconds and some valid requests take 40 seconds, a 10-second timeout will cut off requests during shutdown.

Use the following table as a starting point:

| Workload Type | What to Measure | Considerations |
|---|---|---|
| Short REST APIs | p95/p99 latency and active requests | Grace period larger than valid long processing durations |
| Reporting or export APIs | File generation and response streaming duration | Consider asynchronous jobs or downloading files from object storage |
| Streaming/SSE/WebSocket | Connection lifetime | Needs a reconnect signal protocol or controlled connection closure |
| gRPC streaming | Stream duration and reconnect policy | Drain stream, send completion status, and wait for clients to switch connections |
| Background tasks | Single-job processing time and checkpoints | Stop accepting new jobs, complete or safely return jobs to the queue |

Unbounded long-running requests cannot be guaranteed to finish solely via a shutdown timeout. You need request bounds, cancellation protocols, checkpoints, or resume mechanisms to prevent data loss.

## 9. Stopping Background Tasks and Message Consumers

Embedded web server graceful shutdown focuses on the HTTP server. It does not automatically ensure that every scheduler, executor, message listener, or external consumer stops taking new work at the right time.

For workers or message consumers, the sequence should be:

1. Pause polling or receiving new messages.
2. Wait for already-received messages to finish processing.
3. Acknowledge or commit offsets after successful processing.
4. If unable to finish within the grace period, return messages via retry/requeue or let the broker redeliver according to its semantics.
5. Stop schedulers, executors, and listener containers.
6. Close connections and release resources.

Do not commit offsets before processing succeeds if that could cause message loss. For non-idempotent tasks, design idempotency keys or deduplication mechanisms to handle client retries after an old instance stops.

Beans managing background work can implement `SmartLifecycle` to receive stop signals and invoke callbacks once finished. Design phases appropriately so producers stop emitting work before consumers or workers close resources they still need.

## 10. Consul Deregistration When Spring Boot Stops

Spring Cloud Consul automatically registers the service along the lifecycle when discovery is enabled. The `spring.cloud.consul.discovery.deregister` property enables automatic service deregistration by default when the lifecycle stops.

You can declare this explicitly:

    spring:
      cloud:
        consul:
          discovery:
            register: true
            deregister: true

When the application shuts down normally, Spring Cloud Consul sends a deregister request to the Consul Agent. The service and its associated checks are removed from the agent's registrations and synchronized with the catalog.

The exact order between graceful web-server shutdown and the deregister step is governed by the lifecycle phases of the Spring Cloud/Spring Boot version. Do not assume deregister always finishes before the server stops accepting connections. Therefore, remove the instance from traffic via an explicit drain step before sending SIGTERM; deregistration during shutdown is the final registration cleanup step.

If the application is forcefully killed, the host loses power, or the Consul Agent is unreachable, deregistration may not complete. In that case, Consul's health checks and `health-check-critical-timeout` serve as the fallback mechanism to detect and clean up stale failing registrations.

If `deregister=false` is set, an external process must be responsible for cleaning up registrations. Do not disable automatic deregistration without a tested replacement mechanism.

## 11. Eureka Deregistration and OUT_OF_SERVICE Status

Eureka receives periodic heartbeats from clients. When an instance stops normally, the Eureka client can deregister during lifecycle shutdown. When pulling an instance out of traffic before closing the application, proactively set `OUT_OF_SERVICE` via the `ServiceRegistry` endpoint or Spring Cloud Netflix's pause mechanism.

The two operations have different meanings:

- `OUT_OF_SERVICE`: keeps the registration while no longer treating the instance as a serving endpoint.
- Deregister: deletes the registration from Eureka Server.

Do not rely on lease expiration to drain traffic during a planned deployment. Lease expiration is a mechanism for detecting instances that lost heartbeats; it is not an intentional drain procedure. Verify the Eureka Dashboard and consumer discovery results before stopping the process.

## 12. Kubernetes: preStop and terminationGracePeriodSeconds

Kubernetes sends SIGTERM to the container's process when a Pod begins terminating. Kubelet waits for the termination grace period; once expired, any still-running process receives SIGKILL.

The `preStop` hook runs before SIGTERM is sent, and hook duration also counts toward the termination grace period. You can use the hook to call an internal drain endpoint before Spring Boot receives the stop signal.

Illustrative configuration example:

    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: order-service
          image: example/order-service
          lifecycle:
            preStop:
              exec:
                command:
                  - /bin/sh
                  - -c
                  - "curl -fsS -X POST http://127.0.0.1:8080/internal/lifecycle/drain; sleep 10"

In this example, the image must include `curl`. The drain endpoint transitions readiness to `REFUSING_TRAFFIC`. The 10-second sleep is only an illustrative value to allow EndpointSlice, ingress, or load balancers to update; replace it with durations measured in your actual cluster.

The Pod readiness probe can use:

    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      failureThreshold: 1

If the management server uses a separate port, the readiness probe must target that port. If the drain endpoint resides on the application port, `preStop` must call the application server's address and port.

`terminationGracePeriodSeconds` must be greater than the sum of `preStop` duration, request drain time, and resource closing steps, plus a safety buffer. For example, if `preStop` waits 10 seconds and Spring Boot has a 45-second shutdown phase, 35 seconds remain as buffer within a 90-second total. If actual timeouts exceed the budget, Kubernetes sends SIGKILL and requests may be cut off.

Kubernetes updates EndpointSlice and marks terminating endpoints as no longer ready for normal traffic. Propagation to ingress or load balancers has latency; therefore, the application should still coordinate readiness and draining rather than assuming every consumer stops sending requests instantly.

## 13. Docker and SIGTERM Signals

When running Docker, `docker stop` sends a stop signal to the main process and waits for the stop timeout before forcefully terminating the container. You can set the wait period in Docker Compose:

    services:
      order-service:
        image: example/order-service
        stop_grace_period: 90s

Ensure the JVM is the main process or the entrypoint forwards SIGTERM properly. If a shell script launches Java without `exec`, the signal may not reach the JVM as expected.

Example entrypoint:

    #!/bin/sh
    exec java -jar app.jar

Do not use `docker kill` or SIGKILL for normal shutdowns. SIGKILL prevents the JVM from running shutdown hooks, waiting for requests, and performing lifecycle deregistration.

## 14. Calculating the Shutdown Time Budget

The entire workflow needs a consistent time budget:

    Termination grace period
      >= preStop/drain trigger
       + registry/load balancer propagation
       + in-flight request drain
       + background task drain
       + Spring lifecycle shutdown
       + safety buffer

An illustrative example:

| Phase | Expected Duration |
|---|---|
| Call drain endpoint and mark readiness | 1 second |
| Wait for routing/registry update | 10 seconds |
| Wait for HTTP requests and background tasks | 35 seconds |
| Spring lifecycle shutdown | 20 seconds |
| Buffer | 14 seconds |
| Total termination budget | 80 seconds |

Phases may overlap depending on design; the table is a planning budget, not a fixed Spring Boot timeline. Measure real durations in the deployment environment and ensure platform timeouts exceed what the application needs.

If `spring.lifecycle.timeout-per-shutdown-phase` is 45 seconds while Kubernetes allows only 30 seconds, kubelet may SIGKILL the application before Spring finishes. If `preStop` consumes 20 seconds, the remaining time for SIGTERM and graceful shutdown shrinks accordingly.

## 15. Verifying the Drain Procedure

A test should simulate both short and long requests:

1. Start at least two instances of the same service.
2. Send continuous requests through LoadBalancer or gateway to verify traffic distribution.
3. Initiate draining on one instance via the internal endpoint or registry operation.
4. Inspect readiness status, Eureka/Consul, and the instance list received by consumers.
5. Verify new requests route to the remaining instance.
6. Issue a long-running request on the draining instance and confirm it finishes before the process exits.
7. Send SIGTERM and watch lifecycle logs, server close timing, and deregistration.
8. Verify the registry no longer lists the old instance and consumers do not keep picking its address.
9. Repeat with a running message consumer or background task.
10. Test requests exceeding the timeout to confirm the system handles timeouts, retries, and partial work safely.

Record timestamps for key milestones: drain start, readiness state change, registry update, last request started, last request completed, SIGTERM received, and process exit. These milestones help tune the termination budget with data rather than guesswork.

## 16. Common Shutdown Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| New requests still arrive at stopping instance | Registry/readiness not updated or caches not refreshed | Remove instance from traffic before SIGTERM and verify consumers |
| In-flight requests reset | Grace period too short or SIGKILL used | Increase timeout and measure p99/long processing durations |
| Eureka still displays instance | `OUT_OF_SERVICE` not set or client did not deregister | Check `ServiceRegistry` status, heartbeats, and shutdown logs |
| Consul retains registration | Agent did not receive deregister or deregister disabled | Check lifecycle, ACLs, and `health-check-critical-timeout` |
| Readiness DOWN yet traffic still arrives | Load balancer does not use readiness or calls another registry directly | Integrate readiness with the right routing layer |
| Messages processed twice | Consumer stopped before ack/commit or non-idempotent retry | Design post-processing ack, idempotency, and deduplication |
| Kubernetes kills process before completion | `terminationGracePeriodSeconds` shorter than total shutdown budget | Increase grace period or reduce drain duration in a controlled way |
| Docker does not forward SIGTERM to JVM | Shell entrypoint does not forward signals | Use `exec` so the JVM receives signals directly |
| WebSocket/SSE abruptly disconnected | Connection outlives grace period | Provide reconnect notifications, resume tokens, or connection lifetime bounds |

## 17. Securing Drain Endpoints and Registry Operations

Drain, pause/resume, and `ServiceRegistry` endpoints can stop an instance from receiving traffic. If unauthorized callers can invoke them, they can cause service disruption.

Requirements:

- Expose administrative endpoints only on internal networks.
- Protect with authentication and appropriate roles.
- Restrict state-changing permissions; GET and POST permissions do not need to be identical.
- Use narrowly scoped ACL tokens when calling the Consul Agent API.
- Write audit logs capturing instance ID, old/new status, actor, timestamp, and reason.
- Never embed real tokens in scripts, command history, or repositories.
- Check status before and after draining to avoid affecting the wrong instance.

The drain endpoint should be idempotent: calling it multiple times keeps the instance in the traffic-refusing state. The resume endpoint should be used only after the application and dependencies are ready to serve again.

## 18. Conclusion

A safe shutdown consists of three coordinated steps: pulling the instance out of traffic, waiting for in-flight requests and background work to complete, and closing the application via graceful shutdown. Readiness and registry status help consumers stop selecting the instance; Spring Boot graceful shutdown protects in-flight requests during the wait; `ServiceRegistry` and the provider perform status updates or deregistration.

In a rolling deployment, start and verify replacement instances first, mark the old instance as not accepting traffic, wait for the registry and load balancer to update, drain in-flight HTTP and message/job work, and then send SIGTERM. Spring Boot timeouts, `preStop`, and the termination grace period must be budgeted together. Finally, verify the registry, traffic, and shutdown logs to confirm the instance exited the system as planned.

## References

- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot — Application Availability and Readiness](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot — Actuator Health Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Cloud Commons — ServiceRegistry Actuator Endpoint](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Netflix — Eureka Client Pause and Resume](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Consul — Service Agent HTTP API and Maintenance Mode](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [Kubernetes — Pod Lifecycle and Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)

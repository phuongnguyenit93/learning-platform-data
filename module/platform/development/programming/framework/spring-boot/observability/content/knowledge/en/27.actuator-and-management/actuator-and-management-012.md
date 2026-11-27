# Shutdown Endpoint

In the **Actuator and Management** chapter of the **SPRING_BOOT_OBSERVABILITY** module, the Shutdown endpoint is an administrative endpoint that allows requesting a Spring Boot application to stop by closing its `ApplicationContext`. It is useful in certain controlled operational workflows, but it can also stop an instance from serving traffic as soon as it is called. Therefore, this endpoint is typically disabled and unexposed by default and must be treated as a privileged operation.

Distinguish the **Shutdown endpoint** from web server **graceful shutdown**. The endpoint issues the command to close the application; graceful shutdown is the mechanism allowing the server to stop accepting new requests and give in-flight requests time to finish within a configured limit. Simply enabling the endpoint does not guarantee traffic has already drained from the load balancer, schedulers have stopped cleanly, or all background work has completed. Coordination with the orchestration platform, readiness, and application lifecycle still needs to be designed.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Explain what action the Shutdown endpoint performs in Spring Boot.
2. Distinguish endpoint enablement, HTTP exposure, and authorization.
3. Understand why the Shutdown endpoint must be protected as a privileged administrative operation.
4. Send a shutdown request via HTTP POST under appropriate configuration.
5. Configure graceful shutdown for the embedded web server.
6. Understand the role of `spring.lifecycle.timeout-per-shutdown-phase`.
7. Coordinate readiness, load balancers, and orchestration before stopping an instance.
8. Assess the impact on in-flight requests, scheduled tasks, and message consumers.
9. Write integration tests for the endpoint, security, and shutdown lifecycle.
10. Build a controlled runbook to stop an instance without disrupting the whole system.

## 2. What Is the Shutdown Endpoint?

Spring Boot Actuator provides the `shutdown` endpoint to request closing the application's `ApplicationContext`. When enabled and exposed over HTTP, the endpoint accepts a POST request and triggers context shutdown.

This endpoint has important characteristics:
- It is a state-mutating operation, not a read-only info endpoint.
- It is typically disabled by default.
- It must be both enabled and exposed over HTTP before it can be called.
- Security policies must restrict which callers are allowed to invoke it.
- After shutdown succeeds, the instance will no longer serve new requests.

Example HTTP call:

~~~http
POST /actuator/shutdown
~~~

The actual path depends on the management base path, management port, and web exposure configuration. If the base path changes to `/manage`, the corresponding endpoint is `/manage/shutdown`.

Do not send this POST to all replicas or a service load-balanced endpoint if the goal is to stop a single instance. Identify the exact target instance before invoking it.

## 3. Enablement, Exposure, and Authorization

Three layers to distinguish:

| Layer | Question | Configuration/Control |
| --- | --- | --- |
| Enablement | Is the endpoint created and allowed to operate? | management.endpoint.shutdown.enabled |
| Exposure | Is the endpoint accessible over HTTP/JMX? | management.endpoints.web.exposure or JMX exposure |
| Authorization | Who is allowed to send a shutdown request? | Spring Security role, network policy, and operator identity |

An enabled endpoint is not necessarily exposed. An exposed endpoint also does not mean anonymous callers are allowed to invoke it. In production, all three layers must be controlled together.

Example enabling the endpoint and exposing it selectively:

~~~yaml
management:
  endpoint:
    shutdown:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,shutdown
~~~

This configuration only illustrates enablement/exposure. It does not replace authentication, authorization, or network isolation. Do not use a wildcard include just to enable Shutdown; the exposure list should only contain genuinely needed endpoints.

If the endpoint is not enabled, requests may return 404 or not appear in endpoint mappings depending on version/configuration. If enabled but not exposed, the HTTP URL remains unreachable.

## 4. Calling the Shutdown Endpoint

When the endpoint is enabled, exposed, and the caller is authorized, send an HTTP POST:

~~~bash
curl -X POST http://localhost:8080/actuator/shutdown
~~~

If using a separate management port:

~~~bash
curl -X POST http://localhost:9091/actuator/shutdown
~~~

Illustrative example response:

~~~json
{
  "message": "Shutting down, bye..."
}
~~~

The exact response may vary by Spring Boot version. Once the request is accepted, the `ApplicationContext` begins closing and the HTTP connection may terminate as the server shuts down. Do not treat the response body as sole proof that all work has drained or all resources have closed cleanly.

If authentication is used, pass credentials through your operational environment's secure mechanism. Avoid recording tokens in shell history, URLs, process arguments, or automation logs.

## 5. Shutdown Endpoint and Graceful Shutdown

These two mechanisms are related but serve different purposes:
- **Shutdown endpoint**: issues the command to close the Spring `ApplicationContext`.
- **Graceful web server shutdown**: stops accepting new requests and gives in-flight requests time to finish before the server stops.

Graceful shutdown can be configured:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

`server.shutdown: graceful` instructs the embedded server to support graceful shutdown. `spring.lifecycle.timeout-per-shutdown-phase` sets the maximum wait time per lifecycle shutdown phase, not a single global deadline for every resource across the entire application.

When the context closes, lifecycle-managed components are asked to stop in phases. The web server can stop accepting new requests and wait for active requests within the timeout. If the timeout expires, remaining activities may be terminated. Verify behavior for your server implementation and Spring Boot version.

Graceful shutdown does not guarantee:
- In-progress consumed messages are committed if the handler does not support graceful stop.
- Long-running scheduled tasks finish without lifecycle coordination.
- Database transactions are held open indefinitely.
- Requests exceeding the timeout will always complete.
- The load balancer has already stopped sending traffic before shutdown starts.

## 6. Readiness and Traffic Draining

In environments with a load balancer or Kubernetes, remove the instance from traffic before closing the context.

~~~mermaid
sequenceDiagram
    participant Ops as Operator / Orchestrator
    participant LB as Load balancer
    participant App as Spring Boot instance
    participant Work as In-flight work

    Ops->>App: Mark instance unready
    App-->>Ops: Readiness DOWN
    Ops->>LB: Remove instance from targets
    LB-->>App: Stop routing new requests
    Note over App,Work: Wait for propagation and in-flight work
    Ops->>App: Initiate shutdown
    App->>Work: Stop accepting new work / drain
    Work-->>App: Complete or reach timeout
    App-->>Ops: Context closed
~~~

Readiness DOWN does not automatically guarantee the load balancer has updated its target list. Wait for the platform's propagation/drain interval and verify in practice. In Kubernetes, readiness probes cause a pod to be removed from Service endpoints once the control plane updates; that update is not instantaneous.

Do not use liveness DOWN as a way to drain traffic. A liveness failure can cause the platform to restart the container, creating a restart loop or killing the process before draining finishes.

If a standardized drain operation is needed, coordinate readiness state, load balancer deregistration, and shutdown in an explicit workflow. The Shutdown endpoint is only one of the final steps.

## 7. Background Tasks and Message Consumers

An application may have scheduled tasks, `@Async` executors, message listeners, or batch jobs running when shutdown starts. Graceful web server shutdown does not automatically handle all of these workloads.

Consider individually:
- **Scheduled tasks**: do not start new runs while the application is stopping; define handling and timeouts for active runs.
- **Message consumers**: stop pulling new messages, finish or roll back current messages, and commit/ack according to broker semantics.
- **@Async executors**: configure `wait-for-tasks-to-complete` and `await-termination` appropriately.
- **Batch jobs**: save checkpoints or state for safe resumption.
- **Database transactions**: ensure rollback when execution is canceled; do not hold connections indefinitely.
- **External locks**: release locks via proper lifecycle hooks or rely on leases/TTLs to recover when a process is killed.

Tasks need idempotency in case they are interrupted mid-way and rerun after the instance starts. Do not assume a shutdown signal always arrives before a container is forcibly terminated.

## 8. Securing the Shutdown Endpoint

The Shutdown endpoint can cause denial of service if unauthorized callers can invoke it. Protections:
1. Do not expose the endpoint without a clear operational use case.
2. If needed, expose it only on a dedicated management interface/port.
3. Use strong authentication and a specialized role, e.g., `ROLE_INSTANCE_ADMIN`.
4. Restrict network access via firewalls, private networks, or Kubernetes NetworkPolicies.
5. Audit the caller, target instance, timestamp, and outcome of the operation.
6. Do not place the endpoint behind a standard public ingress.
7. Do not embed credentials in URLs or scripts whose command lines are logged.
8. Require operational approval/change procedures where mandated by the environment.

Illustrative `SecurityFilterChain` example:

~~~java
@Configuration(proxyBeanMethods = false)
class ManagementSecurityConfiguration {

    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(EndpointRequest.to("health"))
                        .permitAll()
                        .requestMatchers(EndpointRequest.to("shutdown"))
                        .hasRole("INSTANCE_ADMIN")
                        .anyRequest()
                        .hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

This is an illustrative example. If the application has multiple `SecurityFilterChain` beans, verify matchers/ordering so the shutdown endpoint is not caught by a broader chain allowing anonymous access. Roles must be mapped from a trusted identity provider.

### Separate Management Port

~~~yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
~~~

Binding loopback is only suitable when administrative callers run in the same network namespace or go through a controlled local proxy. In containers, operators from other nodes generally cannot reach loopback inside a container. Choose bind addresses and network policies based on actual topology; a separate management port does not automatically create a complete security boundary.

## 9. Timeouts and Lifecycle Phases

When closing the `ApplicationContext`, Spring lifecycle-managed beans are stopped in phases. `spring.lifecycle.timeout-per-shutdown-phase` defines the wait time for each phase. If there are multiple phases, total shutdown time can exceed this value.

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

Choose the timeout based on P99 duration of active requests, load balancer/orchestrator drain time, message listener stop time, executor task wait time, database transaction commit/rollback time, and the grace period allowed by the platform before a kill signal.

For example, if the platform gives only 30 seconds before `SIGKILL` while the application needs 45 seconds per shutdown phase, the process may be killed before lifecycle completion. Align application timeouts with `terminationGracePeriodSeconds` or the platform's equivalent limit.

Do not set an infinite timeout to avoid dropping requests. A hung task could stall shutdown indefinitely and prevent deployment rollouts from finishing.

## 10. Shutdown Hooks and Operating System Signals

Spring Boot typically integrates with a JVM shutdown hook to close the `ApplicationContext` when the process receives an appropriate shutdown signal. Container orchestrators usually send `SIGTERM` first, wait for a grace period, and then send `SIGKILL` if the process has not exited.

The Shutdown endpoint and OS signals can both lead to context closure, but their entry points differ:
- The endpoint is called over HTTP by an operator/automation.
- `SIGTERM` is sent by a process manager/orchestrator.
- The JVM shutdown hook coordinates context close during process lifecycle.

Do not call `System.exit()` as a routine substitute for the Spring lifecycle. Doing so improperly can bypass resource management sequences provided by the framework. To stop an application intentionally in code, prefer appropriate lifecycle/context APIs and understand who owns the `ApplicationContext`.

## 11. Observability for the Shutdown Process Itself

Shutdown is an operational event that should be recorded. Use logs and metrics to answer:
- Who or which component initiated shutdown?
- Which instance was requested to stop?
- Did readiness transition to DOWN?
- How many requests/tasks were active?
- Which lifecycle phase took the longest?
- Did any component time out or fail to stop?
- Did the process exit cleanly or get killed by the orchestrator?

Log events should include service/instance identity, reason category, trigger source, and timestamp. Do not log credentials or raw authorization headers.

Example log event:

~~~java
log.atInfo()
        .addKeyValue("event.name", "application.shutdown.requested")
        .addKeyValue("trigger.source", "operator")
        .addKeyValue("shutdown.mode", "graceful")
        .log("Application shutdown requested");
~~~

You can use an `ApplicationListener` for lifecycle events like `ContextClosedEvent` to record when the context begins closing. These events are not proof that every bean has finished stopping; track the outcome of each lifecycle component and process exit.

Do not try to export a new trace to the backend after the exporter has already begun shutting down. If auditing is needed, use a log/metric pipeline with clear flush/close ordering and check the exporter shutdown timeout.

## 12. Testing the Shutdown Endpoint

Endpoint tests must be isolated because a valid request can close the test's `ApplicationContext`. You can verify enablement/exposure/security in an isolated test context or use integration tests that launch an independent process.

Test categories:
1. Endpoint is inactive when not enabled.
2. Endpoint is unreachable over HTTP when not exposed.
3. Anonymous callers are rejected.
4. Insufficiently privileged roles are rejected.
5. Appropriate admin roles can send POST in an isolated test environment.
6. Graceful shutdown stops accepting new requests per server semantics.
7. In-flight requests are allowed to complete within the configured timeout.
8. Lifecycle-managed beans receive stop callbacks properly.
9. Scheduled/message consumers stop accepting new workload.
10. Process exits before the platform grace period in normal scenarios.

Example testing security/exposure using a test context without triggering an actual shutdown:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ShutdownEndpointSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithAnonymousUser
    void anonymousCannotShutdown() throws Exception {
        mockMvc.perform(post("/actuator/shutdown"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Actual status may be 401 or 403 depending on authentication/authorization setup. Tests require matching endpoint exposure/security config and must not send an authorized shutdown request to a shared test-suite `ApplicationContext`.

## 13. Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| /actuator/shutdown returns 404 | Endpoint not enabled or not exposed; different base path. | Check enablement, exposure, and base path. |
| POST returns 401 | Caller not authenticated. | Check credentials/identity provider. |
| POST returns 403 | Caller authenticated but lacks role. | Check role mapping and SecurityFilterChain. |
| POST accepted but process does not exit immediately | Lifecycle phases or in-flight work waiting. | Check shutdown logs, timeouts, and bean lifecycles. |
| Active requests interrupted | Graceful shutdown disabled or timeout too short. | Check `server.shutdown` and `timeout-per-shutdown-phase`. |
| Pod gets SIGKILL before shutdown completes | Platform grace period shorter than needed time. | Align application timeout with orchestrator termination grace. |
| Instance still receives traffic as shutdown starts | Readiness/load balancer not drained before endpoint call. | Check deregistration and propagation delay. |
| Scheduled task aborted mid-run | Task lacks graceful lifecycle/checkpointing. | Design cancellation, checkpoints, and idempotency. |
| Duplicate message processing | Inappropriate ack/commit or listener shutdown semantics. | Check broker listener stop/ack/rollback behavior. |
| Shutdown hangs | Bean stop callback hung or executor waiting indefinitely. | Find slow lifecycle phase and bound wait times. |

## 14. Runbook: Controlled Shutdown of a Spring Boot Instance

1. Identify the exact instance/pod/container to stop; do not use a service-wide load-balanced address.
2. Confirm sufficient replicas/capacity remain to continue serving traffic.
3. Check alerts, active requests, queue backlogs, and scheduled/batch workloads.
4. Transition the instance to not-ready or deregister it from the load balancer.
5. Wait for readiness propagation and connection draining per platform policy.
6. Verify new requests are no longer routed to the instance.
7. Send `POST /actuator/shutdown` over the management network with an authorized identity, or use the orchestrator's standard lifecycle signal per procedure.
8. Monitor logs for `ContextClosedEvent`, graceful server shutdown, and component stops.
9. Verify in-flight requests/tasks finish or terminate per timeout policy.
10. Confirm the process/container exit code and that it did not receive `SIGKILL`.
11. Check replica/service capacity after the instance stops.
12. Record the audit event and update the incident/change record if applicable.

If the shutdown endpoint is not needed for day-to-day operations, keep it disabled and use standard orchestration/lifecycle signals to stop processes.

## 15. Self-Check Exercises

### Exercise 1 — Endpoint Available but Returns 404

You added Actuator, yet `POST /actuator/shutdown` returns 404. What must you check?

**Answer:** Whether the Shutdown endpoint is enabled, whether it is exposed over HTTP, and whether the base path/management port is correct. Having the Actuator starter does not automatically make the shutdown endpoint public.

### Exercise 2 — GET or POST?

Should `GET /actuator/shutdown` be used to check the endpoint?

**Answer:** No. Shutdown is a state-changing operation and uses POST. Do not use GET for destructive operations.

### Exercise 3 — Graceful Shutdown

The Shutdown endpoint is enabled, yet active requests are terminated immediately. Which configurations should you inspect?

**Answer:** Check `server.shutdown=graceful`, `spring.lifecycle.timeout-per-shutdown-phase`, the web server implementation, and the platform grace period.

### Exercise 4 — Kubernetes Rollout

A pod receives shutdown while still Ready and the load balancer keeps sending requests. Which step is missing?

**Answer:** Readiness transition/deregistration and waiting for traffic draining before requesting shutdown. The endpoint does not coordinate external load balancers on its own.

### Exercise 5 — Scheduled Tasks

A scheduled task is running when `ApplicationContext` closes. Does graceful web server shutdown guarantee the task finishes?

**Answer:** No. You must separately manage scheduler/executor lifecycle, cancellation, timeouts, and checkpoints/idempotency.

### Exercise 6 — Platform Timeout

The application needs 45 seconds to stop, but the orchestrator only waits 20 seconds before `SIGKILL`. What can happen?

**Answer:** The process gets killed before lifecycle shutdown finishes. Align `timeout-per-shutdown-phase` and the orchestrator grace period with actual drain time.

## 16. Deployment Checklist

- [ ] A clear operational use case exists for the Shutdown endpoint.
- [ ] Endpoint stays disabled if not needed.
- [ ] If enabled, exposed only via a controlled management interface/network.
- [ ] Authorization uses a specialized administrative role.
- [ ] Operations use HTTP POST and target the exact instance.
- [ ] Shutdown is never invoked via a public load-balanced service address.
- [ ] Graceful web server shutdown is configured when needed.
- [ ] `spring.lifecycle.timeout-per-shutdown-phase` fits the workload.
- [ ] Platform termination grace period exceeds the required drain time.
- [ ] Readiness/deregistration and traffic drain complete before shutdown.
- [ ] In-flight requests have reasonable time limits.
- [ ] Scheduled tasks, message consumers, and executors have clear stop semantics.
- [ ] Batch/consumer work has checkpoints, ack/rollback, and idempotency.
- [ ] Logs/audits record trigger source and outcome without credentials.
- [ ] Integration tests cover enablement, exposure, authorization, and lifecycle.
- [ ] Runbook verifies clean process exit, capacity, and replica health after shutdown.

**Takeaway:** The Shutdown endpoint instructs Spring Boot to close the `ApplicationContext`; graceful shutdown helps the web server stop accepting new requests and wait for in-flight work within a deadline. In production, drain traffic via readiness/load balancers, protect the endpoint with authorization and network policies, coordinate schedulers/message consumers/executors, and align application timeouts with platform grace periods. If there is no specific administrative need, keep the endpoint disabled.

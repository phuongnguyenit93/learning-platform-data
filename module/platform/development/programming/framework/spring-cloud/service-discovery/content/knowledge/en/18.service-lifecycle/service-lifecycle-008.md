# Rolling Update, Blue-Green, and Instance Overlap Duration

When deploying a new version of a microservice, old and new versions typically must coexist for a period of time. This overlap window keeps the system serving requests while new instances start up, pass readiness checks, register with the registry, and become visible to consumers. If old instances are stopped too early, consumers may still hold old addresses in cache or not yet know the new instances are ready.

In a Spring Cloud system, rolling updates and blue-green deployments must coordinate three lifecycles: the process/container lifecycle, status in Eureka or Consul, and the instance-list cache in consumers/LoadBalancer. A successful deploy reported by the orchestrator does not prove every consumer has switched to the new endpoints.

## 1. Why Is Overlap Duration Needed?

Suppose `inventory-service` currently has three instances on version `v1`. When deploying `v2`, you should not stop all three old instances before starting new ones. Consumers could hit a window with no available instances, or keep calling old addresses even though processes have stopped.

Overlap duration allows:

- New instances to start, load configuration, connect to dependencies, and finish warm-up.
- Readiness probes to confirm instances can receive requests.
- Eureka/Consul to record new statuses and update registries/caches.
- Consumers to fetch or observe changes, after which LoadBalancer starts selecting new instances.
- Old instances to stop receiving new requests, finish in-flight requests, and close resources cleanly.

It is important to distinguish:

| Concept | Meaning |
|---|---|
| Process overlap | Old and new processes coexist on infrastructure |
| Discovery overlap | Both old and new instances appear in the registry simultaneously |
| Traffic overlap | Consumers can select both old and new instances to handle new requests |
| Drain period | Old instances stay running to finish already-accepted requests/connections while accepting no new traffic |

In a rolling update, traffic overlap is usually acceptable when both versions have compatible APIs and data. In blue-green, traffic overlap is typically controlled via a gateway, separate service IDs, or weighted routing mechanisms.

## 2. How Does a Rolling Update Work?

A rolling update replaces batches of old instances with new instances. In a Kubernetes Deployment, the `RollingUpdate` strategy uses two primary parameters:

| Property | Meaning |
|---|---|
| `maxSurge` | Number of Pods allowed to be created above the desired replica count during an update |
| `maxUnavailable` | Maximum number of Pods allowed to be unavailable during an update |

Suppose a Deployment has `replicas: 4`, `maxSurge: 1`, and `maxUnavailable: 0`: Kubernetes can spin up one extra new Pod, but must keep all four Pods ready before removing another old Pod. This requires spare CPU/RAM capacity to run the extra Pod during overlap.

Abbreviated manifest example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  minReadySeconds: 10
  progressDeadlineSeconds: 600
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
        - name: inventory-service
          image: example/inventory-service:2.0.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /actuator/health
              port: http
            periodSeconds: 5
            failureThreshold: 30
```

`maxSurge` and `maxUnavailable` can be absolute counts or percentages. With percentage values, Kubernetes rounds `maxSurge` up and `maxUnavailable` down. Both default to 25%. Choose values based on replica count, cluster capacity, and the minimum availability you must maintain.

`minReadySeconds` requires a Pod to remain continuously Ready for that duration before the Deployment considers the rollout to have progressed. It does not replace waiting for registry or consumer caches to update.

## 3. Readiness Must Reflect Traffic-Serving Capability

Readiness answers the question: can this instance accept new requests right now? Liveness answers a different question: is the process alive enough to keep running? Do not use liveness in place of readiness.

In Spring Boot, you can enable Kubernetes probes:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
```

Spring Boot provides `/actuator/health/liveness` and `/actuator/health/readiness`. At startup, an instance may be alive yet unready because it is warming up, running compatible migrations, loading caches, or waiting for essential dependencies. During that time, readiness should be `REFUSING_TRAFFIC`; liveness can remain `CORRECT`.

Do not include every dependency in liveness. If a database temporarily loses connectivity and liveness fails, the orchestrator may restart instances en masse while the system is already overloaded. Readiness should evaluate only dependencies genuinely needed for requests the service commits to serving.

**Important note:** Kubernetes readiness controls only Pod Ready status and Kubernetes Service endpoints. It does not automatically change status in Eureka or Consul. If consumers look up instances via Eureka/Consul, configure health integration or the corresponding pause/deregister workflow so the registry reflects that state.

## 4. Register New Instances Before Pulling Old Instances

General safe rolling-update sequence:

1. Create a new instance with the new version.
2. Wait for the application to start, connect to dependencies, and finish warm-up.
3. Let readiness transition to ready.
4. Confirm Eureka/Consul has received the new instance with the appropriate status.
5. Wait for consumers/LoadBalancer to see the new instance; send a smoke test through the real call path.
6. Choose an old instance to stop receiving new requests.
7. Update discovery status or deregister the old instance.
8. Wait for caches and routing to stop selecting the old instance.
9. Drain in-flight requests, connections, and messages.
10. Send SIGTERM / close the application context and exit the process.
11. Repeat with the next old instance.

In Kubernetes, controllers manage the rollout via Pod readiness and EndpointSlice. In Eureka/Consul, discovery state may have its own latency. If both mechanisms coexist, verify both rather than relying solely on Deployment status.

## 5. Eureka During a Rolling Update

Eureka receives registration metadata and heartbeats from each instance. With common configurations, the default heartbeat is 30 seconds and lease expiration is 90 seconds. When an instance shuts down cleanly, Eureka Client sends cancel/unregister during shutdown; if the process dies abruptly, the server must wait for lease expiration or health/status updates.

### 5.1. Ensure New Instances Are Advertised Only When Ready

By default, Eureka relies on heartbeats to determine whether a client is alive. To propagate the application's Actuator status to Eureka, enable health check integration:

```yaml
eureka:
  client:
    healthcheck:
      enabled: true
```

Place this property in `application.yml`, not in `bootstrap.yml`. When enabled, application health status can influence Eureka instance status; default consumers typically use only `UP` instances.

Do not assume Kubernetes readiness automatically updates Eureka. Check instance status on the Eureka Dashboard/API and verify consumers actually filter for `UP` status.

### 5.2. Pulling Old Instances Out of Traffic

Spring Cloud Commons provides actuator pause/resume when the corresponding endpoints are enabled. Calling `/actuator/pause` puts the Eureka instance into `OUT_OF_SERVICE`, helping consumers stop selecting the instance for new requests after the change propagates to the registry/caches. Calling `/actuator/resume` clears the override and restores application-reported status on the next heartbeat.

This removes the instance from rotation; it does not wait for all in-flight requests to finish. After pausing, wait for consumers to stop selecting the old instance before draining and shutting down.

During a controlled shutdown, Eureka Client usually cancels registration. On an abnormal shutdown, the default lease can keep the record alive longer. Do not use the 90-second lease expiration as a drain time; leases are a mechanism to detect lost clients, not a graceful deployment workflow.

### 5.3. Propagation Latency

Spring Cloud Netflix explains that an instance can take up to three heartbeat intervals for metadata to synchronize across instance, server, and client. With a default 30-second heartbeat, typical situations may take around 90 seconds; Netflix Eureka also notes that server caches and client delta fetches can cause changes to take up to roughly two minutes to reach consumers.

This describes propagation and caching, not a fixed SLA. Peer replication, server response caches, registry fetch intervals, networking, and LoadBalancer caches can alter actual timings. Measure on your exact topology.

## 6. Consul During a Rolling Update

Spring Cloud Consul registers the service with the Consul Agent. By default, an HTTP health check calls `/actuator/health` every 10 seconds. If the check fails, the instance transitions to `critical`. Spring Cloud Consul defaults to `deregister=true` to cancel registration when the application shuts down cleanly.

Example health check configuration using the readiness endpoint:

```yaml
spring:
  cloud:
    consul:
      discovery:
        register: true
        deregister: true
        register-health-check: true
        health-check-path: /actuator/health/readiness
        health-check-interval: 10s
```

`health-check-path`, `health-check-interval`, `register`, and `deregister` are producer-side settings. `deregister: true` lets Spring Cloud Consul automatically cancel registration during a controlled shutdown. On the consumer side, enable `query-passing` if you want only instances with passing checks:

```yaml
spring:
  cloud:
    consul:
      discovery:
        query-passing: true
```

`query-passing` defaults to `false`. If consumers do not enable it or filter status appropriately, a `critical` record can still appear in query results depending on the API.

When an old instance transitions readiness to unready, the Consul Agent detects this on the next health check run. With a 10-second interval, do not expect instantaneous reflection. You can proactively call the deregister API in your shutdown workflow or let Spring Cloud Consul deregister automatically when the application context closes.

`health-check-critical-timeout` can instruct Consul to automatically deregister a service if critical state lasts beyond a threshold; this is a record-cleanup policy, not a draining mechanism. Do not set the threshold too short if instances can recover after a transient network issue.

## 7. Calculating Overlap Duration

Do not pick an overlap duration from a single default number. Measure these milestones:

| Symbol | Time Interval |
|---|---|
| `T_ready` | From new process start until readiness passes |
| `T_registry` | From readiness until the registry records the new status |
| `T_consumer` | From registry update until key consumers see the new instance |
| `T_validation` | Smoke test and verification duration confirming the new version handles requests properly |
| `T_remove_old` | From marking the old instance out of traffic until consumers stop selecting it |
| `T_drain` | Time to finish in-flight requests, connections, and messages |
| `T_margin` | Buffer for jitter, retries, networking, and load variance |

Minimum traffic overlap duration should cover the time for new instances to become visible to consumers and verified:

\[
T_{overlap} \ge T_{registry} + T_{consumer} + T_{validation} + T_{margin}
\]

The old process must stay alive for routing removal and draining:

\[
T_{old\_alive\_after\_cutoff} \ge T_{remove\_old} + T_{drain} + T_{margin}
\]

Illustrative example: new readiness passes after 25 seconds; registry and consumers take 70 seconds to see the instance; smoke testing takes 15 seconds; buffer is 20 seconds. Traffic overlap needs at least roughly 105 seconds after readiness/registration begins (excluding the 25-second startup time if counting from process creation). When retiring an old instance, if removal propagation takes 40 seconds and the longest request needs 30 seconds to finish, the old process must stay alive at least 70 seconds plus margin.

Measure p95/p99 propagation and longest request duration instead of using averages. If the system uses WebSockets, streaming, large uploads, or long tasks, calculate `T_drain` for those connection types or define dedicated bounds/session migration policies.

## 8. How Does Blue-Green Deployment Differ from Rolling Update?

Blue-green maintains two independent environments or instance groups:

- **Blue:** the current version serving production.
- **Green:** the new version deployed and verified before receiving production traffic.

Deployment flow:

1. Keep Blue serving traffic.
2. Spin up Green with full capacity, configuration, and dependencies.
3. Wait for Green readiness and health checks to pass.
4. Test Green via an internal route or dedicated smoke-test URL.
5. Shift traffic at the gateway, ingress, or load balancer to Green (can be shifted incrementally if weighted routing is supported).
6. Monitor error rates, latency, saturation, and business metrics.
7. Keep Blue alive during the rollback window.
8. Only after Green is stable and old requests have drained, deregister/shut down Blue.

### 8.1. Preventing Discovery from Mixing Blue and Green Unintentionally

If Blue and Green register under the same service ID, such as `payment-service`, a consumer using `DiscoveryClient` + LoadBalancer may receive both instance groups and send traffic to both. That can turn a blue-green cutover into a mixed-version rollout.

Three ways to control this:

- Register separate service IDs, such as `payment-blue` and `payment-green`; the gateway or upstream configuration decides which service ID receives traffic.
- Use version tags/metadata alongside a routing layer capable of filtering or weighted distribution by version.
- Keep discovery scoped per group and perform cutover at the gateway/service mesh instead of letting every consumer pick from a shared list.

With Eureka, metadata does not create routing rules automatically; consumers/LoadBalancer must understand that metadata. With Consul, tags can be used in tag-filtered queries if clients are configured accordingly. Never just add `blue`/`green` tags and assume every consumer filters them automatically.

### 8.2. Rollback Window

In blue-green, Blue should stay ready to restart/accept traffic during a rollback window after cutover. If Green exhibits errors, the gateway can switch traffic back to Blue faster than rebuilding and redeploying the old version.

Rollback is safe only if Green has not introduced data changes incompatible with Blue. Therefore, database migrations, event schemas, and API contracts must support both versions throughout the overlap period.

## 9. Data Compatibility While Both Versions Run

Discovery overlap solves only routing. It does not ensure old and new versions interpret data identically.

Apply the expand-contract strategy for databases:

1. **Expand:** add new columns/tables/indexes in a way that keeps the old version working.
2. **Deploy compatible code:** deploy the new version able to read/write compatibly with both old and new schemas.
3. **Migrate:** backfill or migrate data incrementally while monitoring discrepancies.
4. **Switch:** shift traffic completely to the new version.
5. **Contract:** remove old columns/fields only after no instances or consumers need them.

For message brokers, ensure old consumers can read new messages or new producers still emit compatible schemas. For REST/gRPC, add optional fields first, deprecate old fields later, and avoid changing field semantics while both versions coexist.

## 10. Graceful Shutdown and Connection Draining

Removing an instance from the registry does not mean all in-flight requests have ended. Consumers may still hold connection pools, HTTP keep-alive connections, WebSockets, or long requests. The application needs a drain phase before the process stops.

Spring Boot supports graceful shutdown for embedded web servers. Configure it explicitly:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
```

During shutdown, the embedded server stops accepting new requests in a server-appropriate manner and gives in-flight requests a window to complete. `timeout-per-shutdown-phase` caps the wait time per lifecycle phase; once expired, shutdown proceeds.

With Kubernetes, the `preStop` hook runs before the container receives SIGTERM, and hook execution counts toward `terminationGracePeriodSeconds`. EndpointSlice marks the endpoint terminating; `ready` turns `false`, while `serving` may remain `true` while the endpoint drains. Do not assume external load balancers update instantaneously; test propagation timing.

Abbreviated example:

```yaml
spec:
  terminationGracePeriodSeconds: 45
  containers:
    - name: inventory-service
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
```

`sleep 5` is merely an example of waiting for endpoint/routing propagation in a measured environment. It does not deregister from Eureka/Consul and is not the right fix for every cluster. The grace period must cover `preStop`, Spring Boot graceful shutdown, the longest request, and cleanup:

\[
T_{terminationGrace} \ge T_{preStop} + T_{SpringGracefulShutdown} + T_{cleanup} + T_{margin}
\]

Do not make `terminationGracePeriodSeconds` shorter than the total time the application needs; if exceeded, Kubernetes may send SIGKILL and cut off remaining requests.

For message consumers, stop receiving new messages first, finish or return in-flight messages, commit/ack at the right moment, and only then close connections. For schedulers/leader election, ensure only one version executes non-idempotent tasks if Blue and Green run together.

## 11. Safe Sequence for Retiring an Old Instance

General procedure when proactively retiring an instance:

1. Transition readiness to unready so platform endpoint routing stops sending new requests.
2. Remove the instance from discovery: Eureka `OUT_OF_SERVICE`/pause or Consul non-passing health check/deregister per strategy.
3. Wait for consumers and LoadBalancer to update; confirm the instance is no longer selected for new requests.
4. Stop accepting background jobs and new messages.
5. Drain active requests, connections, and sessions.
6. Send SIGTERM or close the Spring ApplicationContext.
7. Let Spring Boot graceful shutdown finish within the configured timeout.
8. Confirm the registry no longer holds an active record and the process has exited.

The exact order among readiness, registry status, and `preStop` depends on the platform. If registry checks read Actuator readiness, changing readiness can trigger the check; if using Eureka pause or active Consul deregistration, do so before the process closes. Test the actual behavior of lifecycle integration in your application.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Rollout completes yet requests still hit old instances | Consumer registry cache or LoadBalancer cache has not updated | Measure propagation; keep old processes alive for removal + drain duration |
| New Pod Ready yet Eureka lacks the instance | Kubernetes readiness does not update Eureka; Eureka registration/health integration is slow | Check Eureka registration, `healthcheck.enabled`, and `UP` status |
| Consul shows old instance critical yet consumers still pick it | Consumers do not enable `query-passing` or do not filter health state | Enable `spring.cloud.consul.discovery.query-passing=true` if only passing instances are desired |
| Both Blue and Green receive traffic | Registered under the same service ID and consumers do not filter by version | Use separate service IDs or controlled routing rules |
| In-flight requests reset when Pod stops | Grace period too short, no draining, or SIGKILL occurred | Increase grace period appropriately, enable graceful shutdown, and measure longest requests |
| No instances available during rollout | `maxUnavailable` too high, new instances not ready, or old instances pulled too early | Use surge capacity, proper readiness, and sufficient overlap |
| Rollback fails to run | Schema/data changed incompatibly with old version | Use expand-contract and preserve compatibility during the rollback window |
| Consul critical record lingers | Critical check does not deregister immediately | Configure appropriate critical timeout or proactively deregister on shutdown |
| Background jobs run twice during overlap | Blue and Green both run uncoordinated schedulers/consumers | Use leader election, distributed locks, or disable jobs in one group |

## 13. Monitoring Rollouts and Deciding When Overlap Ends

Monitor these metrics:

- Instance counts by version, service ID, readiness status, and registry status.
- Timestamps when new instances register, transition to `UP`/passing, and appear in consumers.
- Request counts by version and error rate per instance.
- In-flight requests, open connections, WebSockets/sessions, and unacknowledged messages on old instances.
- p95/p99 latency, timeouts, retries, 5xx responses, and CPU/RAM saturation.
- Time from retirement until no consumers select the old instance.

End overlap only when:

1. New instances are visible to all required consumers.
2. Smoke tests and business checks pass.
3. New traffic has shifted away from the old group.
4. Requests/connections/messages on the old group have drained or been handled per policy.
5. The rollback window has ended and schema/data compatibility allows removing the old version.

Do not use `Deployment Available` status or registry dashboard instance counts as the sole criterion.

## 14. Practicing Rolling Update and Blue-Green

### 14.1. Rolling Update

1. Run three replicas of `inventory-service:v1` and verify consumers call all three.
2. Deploy `v2` with `maxSurge: 1`, `maxUnavailable: 0`.
3. Watch new Pods start up and readiness transition to true.
4. Confirm the registry receives `v2` instances and consumers see the new instances.
5. Generate request load during rollout to confirm `v1` and `v2` both process traffic cleanly.
6. Watch each `v1` instance transition to out-of-service/critical/deregister, then drain.
7. Confirm no new requests hit old instances after routing removal.
8. Verify rollout completion with no abnormal error spikes.

### 14.2. Blue-Green

1. Keep `payment-blue` serving traffic.
2. Deploy `payment-green` with a separate service ID and the same API contract.
3. Run smoke tests directly against Green.
4. Shift a small percentage of traffic to Green if the gateway supports weighted routing.
5. Monitor errors/latency/business metrics and gradually increase the weight.
6. Switch traffic completely to Green.
7. Retain Blue during the rollback window; if errors appear, switch routing back to Blue.
8. Once verified safe, drain and deregister Blue.

In both exercises, add a long-running request and an in-flight message to verify graceful shutdown genuinely waits for work to finish.

## 15. Deployment Checklist

- [ ] Chosen rolling update or blue-green based on routing and rollback capabilities.
- [ ] Capacity exists for the chosen `maxSurge` and `maxUnavailable` settings.
- [ ] Readiness reflects traffic-accepting ability; liveness reflects only process liveness.
- [ ] Verified readiness is reflected into the right routing and registry systems.
- [ ] New instances are `UP`/passing and visible to consumers before draining old instances.
- [ ] Measured Eureka/Consul propagation, consumer caches, and LoadBalancer latency.
- [ ] If using Consul, consumers filter passing checks when only healthy instances are required.
- [ ] If using Eureka, pause/resume, `OUT_OF_SERVICE`, cancel, and lease expiry are understood.
- [ ] Blue and Green have separate service IDs/routing rules to prevent unintended traffic.
- [ ] APIs, database schemas, and message formats remain compatible during overlap.
- [ ] Old instances stop accepting new requests before draining.
- [ ] `terminationGracePeriodSeconds` suffices for `preStop`, graceful shutdown, and cleanup.
- [ ] Long requests, WebSockets, message consumers, and schedulers/leader election are handled.
- [ ] Rollback window and criteria to end overlap are clearly defined.
- [ ] Rollback tested in staging, not just forward deployments.

## References

- [Kubernetes — Update a Deployment Without Downtime](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/)
- [Kubernetes — Deployment RollingUpdate, maxSurge, and maxUnavailable](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Kubernetes — Pod Termination Lifecycle and preStop](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes — EndpointSlices: ready, serving, and terminating](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Cloud Netflix — Eureka Health Checks, Pause/Resume, and Registration](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Consul — Service Discovery and HTTP Health Check](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)

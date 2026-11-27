# Abrupt Process Termination and Deregistration Time

When an instance stops abruptly, the service registry does not necessarily know immediately that the instance has vanished. The provider may no longer be running, yet its registration still remains in the registry or in consumers' caches. During that window, consumers may still select the old address and encounter connection errors.

**Deregistration time is not a single timer.** At least four milestones must be separated: the process stopping, the registry detecting or receiving a deregister request, the registry data being updated, and consumers stopping use of the old address after caches or DNS refresh. In-flight requests also need their own drain time.

This lesson analyzes that lifecycle in Spring Cloud with Eureka, Consul, and ZooKeeper; it also explains controlled shutdown, how to measure stale registration windows, and how to reduce errors when a process crashes or the network partitions.

## 1. Distinguishing Process Stop, Deregister, and Stopping Traffic

An instance can pass through the following milestones:

1. **Process begins stopping:** receives a shutdown signal, crashes, or loses the host.
2. **Application stops accepting new requests:** readiness transitions to DOWN, and the server or gateway starts draining traffic.
3. **Registration is removed or marked unhealthy:** the provider calls deregister, a health check fails, a lease expires, or a ZooKeeper session is lost.
4. **Registry updates catalog:** the instance disappears or transitions to a non-selectable status.
5. **Consumers update discovery data:** clients re-fetch the registry, receive watcher events, or re-query Consul.
6. **Load balancer stops using stale cache:** the in-memory instance list is replaced.
7. **In-flight requests finish:** already-started connections and requests drain or time out.

Therefore, "removed from the registry" and "no consumer is calling the instance anymore" are two different things. A consumer may still hold a stale cache after the server has deleted the registration. Conversely, a health-aware consumer may stop selecting an instance as soon as its status becomes critical even though the catalog still retains the service record for tracking.

Three additional scenarios must be distinguished:

| Scenario | Can the Provider Perform Deregister? | Primary Detection Mechanism |
|---|---|---|
| Graceful shutdown | Yes, if shutdown hooks and client are still working | Deregister call or session closure |
| Process crash / SIGKILL | No | Heartbeat, lease, health check, or session timeout |
| Network partition | Usually uncertain | Timeouts and connection state; can be mistaken for a process crash |

An unresponsive process is not necessarily dead. It may be hung, experiencing network loss, or simply unreachable from one network segment. The registry needs a grace window to distinguish temporary disruption from a lost instance.

## 2. Graceful Shutdown and Abrupt Shutdown

**Graceful shutdown** gives the application an opportunity to stop in order. The JVM receives an appropriate termination signal such as SIGTERM, Spring closes the ApplicationContext, lifecycle components run stop callbacks, the discovery client can cancel registration, and the HTTP server can drain running requests.

**Abrupt shutdown** happens when a process is forcefully killed, the host loses power, the container runtime stops suddenly, or the JVM crashes. Shutdown hooks may not run; the provider cannot send deregistration. The registry must rely on missed heartbeats, health checks, or session expiration.

| Characteristic | Graceful Shutdown | Abrupt Shutdown |
|---|---|---|
| Chance to run shutdown hooks | Usually yes | Not guaranteed |
| Proactive deregistration | Can be performed | No |
| In-flight requests | Can drain until timeout expires | Can be severed immediately |
| Time for registry to notice | Usually short if deregister succeeds | Depends on heartbeat/check/session timeout |
| Risk of stale registration | Mainly from caches and propagation | From both failure detection and caches |
| Mitigation | Readiness, deregister, drain, stop | Health checks, sensible lease/session settings, retries, and evicting failing instances |

SIGTERM is only a controlled stop request; if the application does not finish within the grace period, the runtime may send SIGKILL. SIGKILL gives the JVM no opportunity to run shutdown hooks. Consequently, you cannot rely solely on deregistration when operating containers or servers.

## 3. A Formula to Understand Removal Time

You can model the time from when an instance actually stops serving until consumers stop selecting it:

\[
T_{\text{stale}} \approx
T_{\text{detect}} +
T_{\text{registry}} +
T_{\text{propagation}} +
T_{\text{consumer-cache}}
\]

Where:

- \(T_{\text{detect}}\): time for the registry or health checker to detect the instance is no longer valid.
- \(T_{\text{registry}}\): time to process deregistration, eviction, or status transition.
- \(T_{\text{propagation}}\): time for new data to reach consumers.
- \(T_{\text{consumer-cache}}\): time discovery or load balancer caches still retain the old instance.

This is an estimation model for locating latency sources, not an SLA guarantee. Some components may overlap; DNS caches, retries, connection pools, and in-flight requests can cause real-world observations to differ.

With graceful shutdown, detection time is replaced by the time for the provider to successfully send deregistration. With abrupt shutdown, detection time is typically the bulk of the latency.

Measure separately:

- Time from process stop until the catalog changes.
- Time from catalog change until consumers receive the updated list.
- Time from when consumers receive the updated list until the last request hits the old instance.
- Time for in-flight requests to complete or fail.

Do not lump everything into a single number if your goal is finding the bottleneck. The registry may delete an instance very quickly while consumers keep using stale caches.

## 4. Eureka: Heartbeat, Lease Expiration, and Eviction

Eureka Client registers an instance with Eureka Server and periodically sends heartbeats to renew its lease. Some commonly encountered Eureka defaults are:

| Configuration | Common Default Value | Meaning |
|---|---:|---|
| eureka.instance.lease-renewal-interval-in-seconds | 30 seconds | Interval at which client sends heartbeats |
| eureka.instance.lease-expiration-duration-in-seconds | 90 seconds | Time without lease renewal before the instance becomes eligible for expiration |
| eureka.server.eviction-interval-timer-in-ms | 60000 ms | Interval at which server runs the eviction task |
| eureka.client.registry-fetch-interval-seconds | 30 seconds | Interval at which client re-fetches registry when fetch is enabled |

These values are common Eureka defaults; Spring Cloud Netflix version, server/client configuration, and deployment environment can change them. Check your actual configuration rather than treating these as fixed timings for every application.

### During Controlled Shutdown

When Eureka Client is still active and shuts down cleanly through its lifecycle, the client can send a cancel registration request to the server. The server removes the instance from the registry without waiting for lease expiration. Consumers may still see the old instance until registry fetch and load balancer caches refresh.

### When the Process Dies Abruptly

There are no new heartbeats and no cancel registration call. The server can only treat the lease as expired after the expiration duration. The eviction task runs periodically to evict expired instances. Thus, detection latency can be roughly lease expiration plus eviction wait time, plus propagation and consumer-side caching.

Eureka has a self-preservation mechanism. When heartbeat counts drop abnormally, the server can pause eviction to avoid deleting instances en masse during a wide network incident. This protects the registry from false eviction but can also keep dead instances visible longer. Do not disable self-preservation just to clear dead instances from the dashboard faster without evaluating the risk of a network partition.

### Related Configuration

Example client configuration:

~~~yaml
eureka:
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
  client:
    registry-fetch-interval-seconds: 30
~~~

Example server configuration:

~~~yaml
eureka:
  server:
    eviction-interval-timer-in-ms: 60000
~~~

These are examples showing configurable milestones. Do not lower leases or eviction intervals too aggressively just to shorten detection time. Flaky networks, CPU pauses, or long GCs can cause healthy instances to be mistaken for dead. Choose values based on network latency, pause durations, system load, and fault tolerance.

### Consumers Still Caching Old Instances

Even after Eureka Server removes a registration, consumers may not have fetched the updated registry yet. Spring Cloud LoadBalancer may also cache the `ServiceInstance` list depending on configuration and version. When requests continue hitting a dead address, consumers need appropriate timeouts and retry policies; retries should be applied automatically only to safely repeatable operations.

## 5. Consul: Health Checks and Deregistering Critical Services

Consul typically uses health checks to determine whether a service is passing. The agent runs HTTP, TCP, gRPC, or TTL checks per configuration. When a check fails, status transitions to critical. Consumers can request only passing instances, such as via the Health API with `passing=1`.

Two milestones must be distinguished:

- **No longer selected:** the service becomes critical and consumers query only passing instances.
- **Registration removed:** the service is manually deregistered or Consul automatically deregisters it after the check remains continuously critical long enough if `deregister_critical_service_after` is configured.

Example service registration:

~~~json
{
  "service": {
    "name": "inventory-service",
    "id": "inventory-node-a",
    "address": "10.20.1.15",
    "port": 8080,
    "checks": [
      {
        "http": "http://10.20.1.15:8080/actuator/health",
        "interval": "10s",
        "timeout": "2s",
        "DeregisterCriticalServiceAfter": "2m"
      }
    ]
  }
}
~~~

In this example, the agent checks every 10 seconds. If the check turns critical and stays continuously critical for the configured deregister duration, Consul can automatically remove the service registration. That duration is not the first detection time; consumers using `passing=1` queries can stop receiving the instance as soon as critical status is recorded.

`deregister_critical_service_after` is a check/service configuration option depending on Consul version. Verify duration limits, syntax, and applicability for the version running. Without this mechanism configured, critical status may remain in the catalog until manually deregistered or handled by another cleanup process.

### When the Consul Agent Also Dies

If only the application dies while the Consul agent stays alive, the agent can keep running checks and mark the service critical. If the agent itself or the node is lost, the server must detect node status through Consul's membership/health mechanism. Node detection time is not the same as the application HTTP check interval.

With agent-bound service registrations, clarify who is responsible for registering, checking, and deregistering. If an application registers via a local agent, the agent holds local state and syncs with the catalog; when the agent dies, node/service cleanup depends on node status and Consul configuration. Do not assume `deregister_critical_service_after` replaces every node-loss detection mechanism.

### Monitoring Consul

You can query services and health status via the HTTP API:

~~~bash
curl http://consul-server:8500/v1/health/service/inventory-service?passing=1
~~~

Results include only instances meeting the query's passing condition. Compare the Health API with the Catalog API to distinguish a service still registered but critical from a deleted service.

## 6. ZooKeeper: Session Timeout and Ephemeral Znodes

ZooKeeper service discovery typically creates an ephemeral znode for each instance. This node is bound to the session that created it and is automatically deleted when the session closes or expires.

### During Controlled Shutdown

The application can proactively delete the znode or close the ZooKeeper session. Once the server processes that operation, the ephemeral node is deleted and consumers receive change events via watchers/caches. If the application uses Curator Service Discovery or Spring Cloud Zookeeper, understand the deregistration lifecycle managed by the library to avoid deleting the node twice or creating manual registrations that duplicate auto-registration.

### When the Process Dies or Loses Network Connectivity

If the JVM is killed or the host loses connectivity, ZooKeeper cannot immediately know the client is dead. The session can remain alive during the timeout window. The client library may emit `SUSPENDED` on disconnect; if the session expires, it emits `LOST`. When the session expires, ephemeral znodes belonging to the old session are deleted.

There is no single fixed timeout across all clusters. Clients request a session timeout; the server negotiates a valid value according to ensemble min/max bounds and `tickTime`. Therefore, ephemeral node deletion time depends on the negotiated session timeout, when the server detects expiration, and how fast consumers process watchers/caches.

### After Reconnecting

If the client experiences only a brief interruption and the session survives, it can reconnect without recreating registration. If the session is `LOST`, the old ephemeral node has been deleted; the application must establish a new session and re-register its node when readiness permits. Consumers must also handle stale caches and re-registered watchers.

Do not use persistent znodes as service registrations without a cleanup mechanism. Persistent nodes do not automatically delete when a client session ends and can leave stale instance addresses indefinitely.

## 7. Comparing Detection Times Across Registries

| Registry | Graceful Shutdown | Abrupt Process Stop | Factors That Can Extend Duration |
|---|---|---|---|
| Eureka | Client cancels registration; consumers still need refresh/cache expiry | Lease expiration followed by eviction | Self-preservation, eviction interval, registry fetch, and LoadBalancer cache |
| Consul | Deregister service or agent updates catalog | Health check turns critical; may auto-deregister after configured duration | Check interval/timeout, node health, deregister duration, and consumer cache |
| ZooKeeper | Close session or delete ephemeral node | Ephemeral node deleted only upon session expiration | Session timeout, reconnect, watcher propagation, and consumer cache |

Do not compare the three registries by a single deregistration timeout number. Eureka relies on heartbeats/leases and eviction; Consul relies on health checks, catalog, and optional critical deregistration; ZooKeeper relies on sessions and ephemeral nodes. Each system has its own state representation and cleanup mechanics.

## 8. Registry Removal Time vs. Time Consumers Stop Calling

An illustrative example with Eureka:

- At second 0, an inventory instance is forcefully killed.
- The server receives no cancel registration.
- The lease remains valid for a period of time.
- After the lease expires, the eviction task processes the instance.
- Consumers periodically fetch the updated registry.
- The LoadBalancer cache updates or its TTL expires.
- New requests no longer pick the old instance.

Suppose configuration and caches cause the server to delete the registration after roughly 90–150 seconds, consumers refresh every 30 seconds, and the LoadBalancer cache remains valid for an extra period; total time consumers might keep trying the old instance exceeds registry removal time. This is only a calculation example from hypothetical settings; self-preservation or custom caches can change outcomes significantly.

With Consul, a check turning critical can exclude the instance from `passing=1` queries before the registration is deregistered. With ZooKeeper, the znode may already be deleted while consumers still hold an old instance list in memory until watchers/caches update.

Therefore, measure both **catalog removal time** and **last request to old instance time**. These two metrics answer different questions.

## 9. Designing Graceful Shutdown in Spring Boot

Spring Boot supports graceful shutdown for embedded web servers. Enable it in configuration:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

When `ApplicationContext` closes, the server stops accepting new connections according to web server capabilities and waits for in-flight requests to finish within the granted shutdown window. Actual duration depends on the server (Tomcat, Jetty, Reactor Netty), Spring Boot version, and lifecycle configuration.

Graceful HTTP shutdown alone does not guarantee all consumers have updated discovery. Coordinate readiness and deregistration:

1. Mark the instance unready to receive new traffic.
2. Prevent ingress/load balancers from sending new requests to the instance.
3. Perform deregistration or let discovery integration handle it during lifecycle shutdown.
4. Allow time for consumers to refresh the registry and for in-flight requests to drain.
5. Close the HTTP server, executors, connection pools, and dependencies in an appropriate order.

Auto-registration/deregistration configuration varies by registry and Spring Cloud version. With Eureka, inspect Eureka Client shutdown behavior and related properties such as `eureka.client.should-unregister-on-shutdown` in your version. With Consul and ZooKeeper, inspect service registry integration, auto-registration, and client close order. Do not assume enabling `server.shutdown: graceful` alone is sufficient to remove the service from the registry.

If the application manages readiness itself, ensure the health endpoint and registry share the same serving state. If readiness is DOWN while the registration still exists, only consumers filtering passing/healthy instances avoid it; consumers without health filtering may still call it.

## 10. Orchestrators and Termination Time

Container runtimes and orchestrators have their own grace periods. When stopping a container normally, the runtime typically sends SIGTERM first and SIGKILL after the wait window expires. Kubernetes uses `terminationGracePeriodSeconds`; `preStop` hooks run inside that grace period, after which the container receives the stop signal per runtime configuration.

Example Deployment:

~~~yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: inventory
          image: inventory-service:1.0
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
~~~

This example only illustrates a buffer before the process receives the stop signal. `sleep` does not itself deregister the service and does not guarantee endpoints have vanished from all consumers. In practice, `preStop` can call an internal endpoint to mark readiness DOWN or trigger draining if the application exposes one. The command must suit the image and must not exceed the grace period.

Kubernetes removes unready Pods from relevant endpoints, but updating EndpointSlice, kube-proxy, ingress, service mesh, and discovery caches has latency. If using both Kubernetes Service and a Spring Cloud registry, decide which layer owns instance selection and traffic draining to avoid the two update mechanisms drifting out of sync.

The termination grace period must accommodate readiness/endpoint propagation, deregistration and discovery propagation if applicable, in-flight request completion, and safe resource closure. If total time exceeds the grace period, the runtime may forcefully kill the process, turning a graceful shutdown into an abrupt one.

## 11. Why Not Set Timeouts Too Low?

Lowering heartbeat intervals, lease expiration, health check intervals, or session timeouts can speed up failure detection, but increases the risk of false positives:

- GC pauses or CPU starvation delay heartbeats.
- Network jitter causes check timeouts even when the service is healthy.
- ZooKeeper leader election or temporary network partitions disrupt sessions.
- Busy Consul agents or slow dependencies cause health checks to fail.
- Overly frequent consumer refreshes increase load on the registry and network.

Choose timeouts based on normal latency and acceptable anomalies. Use multiple signals: internal readiness, agent health checks, heartbeats/sessions, and real request observation. Do not remove an instance just for a single brief timeout if doing so causes continuous flapping.

## 12. Handling Requests During the Stale Registration Window

Even with well-configured registries, there remains a window where consumers can pick a dead instance. Consumers must handle this:

- Set appropriate connect timeouts and response timeouts.
- Perform bounded retries on connection errors when another instance can be chosen.
- Automatically retry only idempotent operations or operations with idempotency keys.
- Use circuit breakers or outlier detection if the system needs to avoid repeatedly selecting failing instances.
- If the instance list is empty, return a meaningful service-dependency error instead of looping infinitely.
- Log serviceId, instance address, connection error, and retry count.
- Never log tokens or sensitive data.

A connection refused error can allow LoadBalancer to try another instance if retry integration is configured. However, not every HTTP error should be retried: validation errors or business rejections will not succeed upon re-sending the request.

## 13. Measuring Deregistration Time in a Lab Environment

You can test each milestone separately using a service with an endpoint returning its instance ID.

Record timestamps:

| Milestone | How to Observe |
|---|---|
| T0 — process stop | Shutdown log or container kill timestamp |
| T1 — health failure/session loss | Check status log, Eureka lease/eviction, or Curator LOST |
| T2 — registry removal | Query Eureka/Consul/ZooKeeper and confirm record/node vanishes or turns critical |
| T3 — consumer refresh | Log the instance list received by consumers |
| T4 — last request to old instance | Request logs at the provider or client trace |

Calculate the intervals:

\[
T_{\text{detect}} = T_1 - T_0
\]

\[
T_{\text{registry}} = T_2 - T_1
\]

\[
T_{\text{consumer}} = T_3 - T_2
\]

\[
T_{\text{last-use}} = T_4 - T_0
\]

With Consul, T2 should distinguish "turned critical" from "deregistered," because those are two different milestones. With ZooKeeper, T2 is when the ephemeral znode is deleted; consumers may still use a stale cache. With Eureka, T2 is when the instance is no longer in the server registry, not when every consumer has finished refreshing.

Run two separate tests:

1. **Graceful:** send SIGTERM or run stop with a grace period; confirm the application deregisters, drains requests, and exits.
2. **Abrupt:** forcefully kill the process in the lab; confirm the registry detects it via lease/check/session and measure how long consumers take to stop picking it.

Never run process-kill or network-loss experiments in production. Repeat multiple times in the lab to observe variance rather than drawing conclusions from a single measurement.

## 14. Operational Checklist

Before deploying service discovery, verify:

1. The application has shutdown hooks and deregisters upon receiving SIGTERM.
2. The HTTP server has graceful shutdown and an appropriate timeout.
3. Readiness is lowered before the instance stops accepting requests.
4. The registry has a mechanism to detect dead processes or lost nodes.
5. Eureka lease/eviction, Consul check/deregister, or ZooKeeper session timeout is understood and tuned appropriately.
6. Consumers refresh registry/caches and do not use stale instances indefinitely.
7. Retries, timeouts, and circuit breakers do not create side effects on write requests.
8. The orchestrator grace period is sufficient for draining and shutdown.
9. Metrics separate catalog removal time from last request to old instance.
10. Graceful stop, abrupt kill, and network partition have been tested in an appropriate environment.
11. Alerts exist when a registration persists while its endpoint is unreachable.
12. A recovery procedure exists when an instance restarts and re-registers.

The key point to remember is: **graceful shutdown can proactively deregister; abrupt shutdown forces the registry to detect the lost instance via heartbeats, health checks, or session timeouts; consumers still need to refresh data and expire stale caches before stopping requests.** Therefore, registration removal time and the time traffic actually stops must be measured and designed separately.

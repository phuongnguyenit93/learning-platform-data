# Eureka Enters Self-Preservation or Continuously Fails Renewals

When Eureka Server enables self-preservation, the dashboard may display a warning that the number of received heartbeats is below the expected threshold. In this state, Eureka restricts eviction of lease-expired instances to avoid mass-deleting services during network interruptions or when many clients temporarily fail to send heartbeats. This protective mechanism prevents widespread registry data loss, but it can allow dead instances to remain in the list.

Another scenario is Eureka Clients continuously failing renewals. The root cause may be the registry URL, DNS, network, TLS, authentication, an overloaded server, JVM pauses, or mismatched lease configurations. Self-preservation is usually the server's reaction to a drop in renewals; by itself, it is not necessarily the reason clients fail to renew.

This article guides you through reading the warning, calculating the renewal threshold, separating client vs. server failures, checking eviction and consumer caches, and resolving issues in a safe sequence. The goal is to restore accurate heartbeats and registry state without accidentally deleting healthy instances.

## 1. What Does Self-Preservation Protect?

Each registered Eureka Client typically sends periodic heartbeats/renewals to signal that the instance is still active. Eureka Server tracks the number of renewals received over a window and compares it against the expected count.

If actual renewals drop below the threshold, the server can activate self-preservation. When active, the server restricts deleting instances solely due to lease expiration. The reason is that a connectivity drop between clients and server can cause heartbeats to vanish even while many providers continue serving requests normally.

~~~mermaid
flowchart TD
    A["Eureka Client sends periodic renewals"] --> B["Eureka Server counts renewals"]
    B --> C{"Are actual renewals below threshold?"}
    C -->|"No"| D["Evict based on lease and server interval"]
    C -->|"Yes"| E["Self-preservation activates"]
    E --> F["Restrict mass eviction"]
    F --> G["Dead instances may remain in registry"]
    D --> H["Registry reflects instance state"]
    G --> H
~~~

Self-preservation does not mean all registration or query requests stop. Clients can still register, renew, or fetch if connectivity works; the key point is that the server avoids mass eviction when heartbeat signals drop abnormally.

### Why Is This Mechanism Needed?

Suppose there are 100 instances and a network glitch prevents 40 instances from sending heartbeats for a few minutes. If the server immediately deletes every lease-expired instance, the registry could remove healthy providers that only temporarily lost their path to Eureka. When the network recovers, clients must re-register, consumers may experience major churn, and extra load ensues.

Self-preservation prioritizes keeping registrations while there is insufficient evidence that instances are truly dead. In exchange, the registry may retain stale addresses until heartbeats return or state is handled by an appropriate operational procedure.

## 2. Understanding the Renewal Threshold

You can estimate the expected renewals per minute from the number of registered instances and the renewal interval:

\[
R_{expected} \approx N \times \frac{60}{T_r}
\]

Where:

- N is the number of instances expected to send heartbeats.
- T_r is the renewal interval in seconds.
- R_expected is the expected number of renewals per minute.

The self-preservation activation threshold is estimated as:

\[
R_{threshold} \approx R_{expected} \times P
\]

P is `renewal-percent-threshold`. The common default is 0.85, though you should check the actual configuration and Eureka version running.

For example, with 100 instances, renewal every 30 seconds, and a 0.85 threshold:

\[
R_{expected} = 100 \times \frac{60}{30} = 200
\]

\[
R_{threshold} \approx 200 \times 0.85 = 170
\]

If the server receives only around 140 renewals during the observed minute, the actual count falls below the expected threshold and self-preservation may activate.

This is an estimation model to understand the trend, not a replacement for Eureka Server's internal algorithm. The server also has threshold update intervals, registry states, startup timing, and other configuration factors. Cross-check the actual dashboard, logs, and metrics before concluding.

### Related Intervals

| Property | Config side | Role |
|---|---|---|
| `lease-renewal-interval-in-seconds` | Eureka Client instance | Interval at which client sends renewals |
| `lease-expiration-duration-in-seconds` | Eureka Client instance | Lease duration before instance can be deemed expired |
| `expected-client-renewal-interval-seconds` | Eureka Server | Renewal interval the server uses for estimation |
| `renewal-percent-threshold` | Eureka Server | Minimum renewal ratio compared to expected |
| `renewal-threshold-update-interval-ms` | Eureka Server | Interval for updating the renewal threshold |
| `eviction-interval-timer-in-ms` | Eureka Server | Interval for running the eviction task |
| `registry-fetch-interval-seconds` | Eureka Client | Interval at which consumers fetch the registry |

Commonly encountered defaults are 30s client renewal, 90s lease expiration, 60s eviction task, and 0.85 renewal threshold. These are not guarantees for every release or application; effective values can be overridden by YAML, environment variables, command-line arguments, or server configuration.

## 3. Recognizing When Self-Preservation Is Active

On the Eureka dashboard, look for warnings related to the renewal threshold or self-preservation. The message usually states that the server is receiving fewer renewals than expected and may be protecting the registry from eviction.

When you see the warning:

1. Record the start time and how long the warning persists.
2. Record the current number of instances in the registry.
3. Record actual renewals and threshold if provided by the dashboard or metrics.
4. Check Eureka Server logs around the time of the state transition.
5. Compare the number of actually running clients against the instance count expected by the server.
6. Check whether many clients are failing simultaneously or only a specific group.

Prolonged self-preservation does not by itself prove the server is broken. It indicates the server is receiving fewer heartbeats than considered normal. Determine whether heartbeats are missing because clients genuinely died, clients cannot connect, or the server cannot keep up.

### Distinguishing Three States

| Observation | Possible meaning | First action |
|---|---|---|
| Self-preservation active, providers still healthy | Heartbeat path may be interrupted or threshold no longer fits | Check renewal transport and actual instance count |
| Self-preservation active, many providers already dead | Registry may be retaining stale registrations | Cross-check each instance against actual process/health |
| Self-preservation off, yet instances not removed | Lease not expired, eviction cycle pending, or record being renewed | Check lease, eviction logs, and renewals |

## 4. Diagnosing Renewal Failures from the Eureka Client

Start with the client's own logs. Determine whether the client registered successfully earlier and which server URL renewal requests are targeting.

### Checking Client Configuration

Example:

~~~yaml
spring:
  application:
    name: inventory-service

eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: http://eureka.internal:8761/eureka/
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
    prefer-ip-address: true
~~~

Check the following:

- Is `register-with-eureka` enabled on providers that must register?
- Does `defaultZone` have the right scheme, hostname, port, and context path?
- Can the client's DNS resolve the Eureka hostname?
- Does the client have a route and firewall rule to the server port?
- Was the instance mistakenly configured as consumer-only?
- Are profiles or environment variables overriding URLs and lease intervals?
- Did the client succeed on initial registration while subsequent renewals failed?

Property names and defaults can vary by version. Check the bound configuration and startup logs, not only YAML files in the repository.

### Classifying Errors by Symptoms

| Sign in client logs | Possible cause | Next check |
|---|---|---|
| Connection refused | Eureka Server not listening, wrong port, or service/network down | Check server listener, port, and route |
| Connect/read timeout | Slow network, firewall drops, overloaded server | Measure latency, packet loss, and server threads/CPU |
| UnknownHostException | Wrong DNS or stale DNS | Check hostname resolution from container/Pod |
| 401 or 403 | Authentication/authorization rejecting requests | Check credentials, proxy, and security rules |
| 404 | Wrong context path or endpoint URL | Check `/eureka/` and reverse proxy rewrites |
| SSLHandshakeException | Wrong truststore, SAN, certificate, or TLS policy | Check certificate chain and hostname |
| 5xx from server/proxy | Server, peer, or gateway error | Cross-check server logs and proxy logs |
| Client has no renewal logs | Client never registered, scheduler not running, or log level hidden | Check lifecycle, beans, and logging config |

Do not infer from a single log line. Correlate request IDs or timestamps across client, proxy, and Eureka Server to see whether requests left the client, reached the proxy, and were handled by the server.

### Testing from the Client's Actual Runtime Environment

Test DNS and TCP connectivity directly from the provider's container or Pod:

~~~bash
getent hosts eureka.internal
curl -v --connect-timeout 3 http://eureka.internal:8761/eureka/apps
~~~

If the registry uses HTTPS or authentication, use the appropriate test URL and credentials. Never print tokens or passwords into shared terminal logs.

The `curl` command only tests endpoint reachability; it does not simulate the full renewal protocol. An HTTP 200 on `/eureka/apps` does not by itself prove the client's renew endpoint works properly.

## 5. Diagnosing the Eureka Server Side

If multiple clients fail renewals simultaneously, inspect the server before tweaking individual clients.

Points to check:

- Is the server process stable; are there restarts or OutOfMemoryErrors?
- Are CPU, heap, garbage collection pauses, and request queues spiking abnormally?
- Are HTTP connection pools or thread pools saturated?
- Do logs show renewal requests arriving at the server or being rejected?
- Is the server receiving traffic from the proxy/load balancer via the right route?
- Can Eureka peers connect and replicate the registry?
- Does the dashboard show actual renewals, expected threshold, and self-preservation state?

### Inspecting the Registry via REST API

Example reading the application list:

~~~bash
curl -H "Accept: application/json" \
  http://eureka.internal:8761/eureka/apps
~~~

Reading a specific application:

~~~bash
curl -H "Accept: application/json" \
  http://eureka.internal:8761/eureka/apps/INVENTORY-SERVICE
~~~

Endpoints may require authentication and a different context path if deployed behind a proxy. Use the exact environment URL and never embed real credentials in documentation or logs.

Cross-check `instanceId`, hostname, IP, port, status, and metadata. An UP record in the registry does not prove the process is alive; call the health endpoint or inspect the process from its host/container.

### Checking Multiple Eureka Peers

In a peer-to-peer Eureka cluster, one server may receive renewals while another peer has not synced properly. Check:

- Do peer URLs point to the right servers and resolve from every node?
- Does the network between peers allow replication traffic?
- Are peers returning 4xx/5xx or timing out?
- Do dashboards/REST APIs of peers differ in instance counts or statuses?
- Is a reverse proxy or load balancer routing requests to nodes in a way that breaks topology?

Do not inspect only one dashboard if production runs multiple Eureka Servers. Query every peer and compare the same application/instance ID.

## 6. Checking Leases and Eviction

The renewal interval, lease expiration, and eviction interval jointly govern how long an instance can linger after stopping heartbeats.

Client example:

~~~yaml
eureka:
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
~~~

Server example:

~~~yaml
eureka:
  server:
    enable-self-preservation: true
    renewal-percent-threshold: 0.85
    expected-client-renewal-interval-seconds: 30
    eviction-interval-timer-in-ms: 60000
~~~

The server properties illustrate common configuration names in Spring Cloud Netflix Eureka Server. Verify the property reference for your running release; some values may be computed or updated periodically by the server.

When a client stops gracefully, it usually has a chance to deregister. When a process crashes or loses power, deregistration does not occur; the server must rely on lease/eviction. If self-preservation is protecting the registry, eviction may be restricted even after the lease expires.

Do not lower `lease-expiration-duration-in-seconds` too aggressively just to clear records quickly. Network jitter, GC pauses, or server overload can cause healthy clients to appear as missing heartbeats. Set leases based on renewal interval, real-world latency, and tolerated disruption.

## 7. Distinguishing Self-Preservation from Stale Consumer Caches

At least two layers can make a consumer keep seeing an old instance:

1. Eureka Server still retains the registration because the lease has not expired or self-preservation restricts eviction.
2. Eureka Client fetched an older snapshot and has not pulled the updated registry yet.

Additionally, the server may use a response cache to serve registry endpoints. Therefore, the moment a record changes inside the server does not necessarily match when every consumer sees that change.

Fetch configuration example:

~~~yaml
eureka:
  client:
    registry-fetch-interval-seconds: 30
~~~

During investigation:

1. Confirm whether the instance still exists in the REST API/dashboard of every Eureka peer.
2. Confirm how many instances the specific consumer sees via DiscoveryClient.
3. Check the registry fetch interval and fetch logs.
4. Check the LoadBalancer cache if the application configures its own cache.
5. Send verification requests and log the actual selected instance.

If the server already removed the record yet the consumer still selects it, focus on fetch/cache propagation. If the server still retains the record, focus on renewals, leases, self-preservation, and eviction.

## 8. Common Causes of Dropping Renewals

### Network or DNS

- Firewall/security group blocking clients from reaching Eureka.
- DNS returning an old address after the server moved.
- Proxy/load balancer resetting connections or rewriting paths incorrectly.
- Packet loss, latency, or unstable routes causing renewal timeouts.

### Client or JVM

- CPU starvation delaying the heartbeat scheduler.
- GC pauses lasting longer than lease tolerance.
- Container throttling or overloaded node.
- Application restarting repeatedly, crash-looping, or never completing registration.
- URL/lease configurations differing across profiles.

### Server or Eureka Cluster

- Server overloaded, GC pauses, or exhausted thread pools.
- Peer replication failing.
- Inconsistent reverse proxy or TLS termination configuration.
- Expected renewal interval mismatched with clients.
- Instance count changed sharply after scaling/deployment before the threshold updated.

### Topology Changes and Thresholds

During scale-down or rolling deployments, the number of clients sending renewals changes. If the threshold is still based on the previous count during an update window, the server may temporarily evaluate renewal volume as low. Conversely, an expected interval mismatch with clients can distort the expected threshold.

Check deployment/scale timestamps, actual instance counts, registry registrations, and threshold update intervals before tuning `renewal-percent-threshold`.

## 9. Ordered Runbook

### Step 1: Determine Scope

- Is one client failing or are many clients failing together?
- One Eureka Server or all peers?
- Are renewals failing continuously or only during a brief window?
- Are providers actually healthy or dead?
- Did self-preservation start right around a network/deploy event?

If only one client fails, prioritize that client's configuration and network path. If many clients across multiple services fail together, check shared server, proxy, DNS, and network infrastructure.

### Step 2: Collect Baseline Metrics

Record:

- Actual number of running instances.
- Number of registrations in Eureka.
- Actual renewals in the last minute.
- Expected renewal threshold.
- Self-preservation state.
- Renewal request success/failure rate.
- Server CPU, heap, GC pauses, and request latency.
- Timestamps of deployments, scaling, or network incidents.

Do not alter configurations before recording a baseline; otherwise, it is hard to tell which change made things better or worse.

### Step 3: Restore the Renewal Flow

Prioritize fixing the root cause:

1. Fix DNS, routing, firewall, or proxy if clients cannot reach the server.
2. Fix URL/context path if requests hit the wrong endpoint.
3. Fix truststore, certificate, or authentication if handshakes/requests are rejected.
4. Relieve server load or restore peers if the server cannot keep up.
5. Adjust client scheduler/resources if the JVM or container is starved.
6. Align expected renewal interval and client renewal interval intentionally.

After fixing, watch renewals climb back up and self-preservation exit protective mode according to your server version's behavior.

### Step 4: Handle Verified Stale Instances

Before deleting records, cross-check each instance against processes, containers/Pods, health endpoints, and service owners. Only clean up records confirmed to have no valid workload remaining.

Prioritize:

- Restoring live providers so they resume renewals.
- Allowing stopping instances to gracefully deregister whenever possible.
- Using an approved operational/admin procedure to remove verified stale records.
- Monitoring peers and consumers after the change.

Eureka provides REST APIs for instance operations, but DELETE endpoints can cause impact if called with the wrong application or instance ID. Only perform this after verifying the exact record and with proper admin authorization; never run bulk deletions merely to clear dashboard warnings.

### Step 5: Verify Consumer Convergence

- Peer REST APIs reflect the expected list.
- Consumers successfully fetch the updated registry.
- DiscoveryClient returns the expected instance list.
- LoadBalancer stops selecting stale endpoints.
- Verification requests succeed through healthy providers.
- Renewal and error rates return to a stable baseline over a sufficient observation window.

## 10. Self-Preservation Configuration: When Should You Change It?

Normally, keep self-preservation enabled in production. It is a safety net when the registry cannot distinguish a heartbeat drop caused by a network partition from many providers actually dying.

Only consider tuning the threshold or disabling self-preservation when:

- You have measured and understood real renewal patterns.
- Expected instance counts and renewal intervals are accurately established.
- Independent health checks or monitoring are sufficiently reliable.
- You explicitly accept the trade-off between fast stale-instance removal and risking accidental removal of healthy instances.
- The change has been tested in staging with a rollback plan.

Configuration example:

~~~yaml
eureka:
  server:
    enable-self-preservation: true
    renewal-percent-threshold: 0.85
    renewal-threshold-update-interval-ms: 900000
~~~

Do not copy example values verbatim if topology and release differ. Verify defaults/effective values using configuration metadata, startup logs, or protected configuration endpoints.

### Why You Should Not Disable Self-Preservation Just to Clear a Warning

If the root cause is a network partition, disabling self-preservation can make the server wipe out registrations of healthy providers. Consumers then lose endpoints and can suffer an outage worse than the initial warning.

If the root cause is that many providers actually died, self-preservation can hold stale records longer. The right fix is verifying provider state, restoring renewals on live instances, and cleaning up confirmed stale records through controlled procedures.

### Test Environments

In an isolated test, you may disable self-preservation to test deterministic lease eviction, but clearly mark it as a test-only setting. Never promote that setting to production without re-evaluating risk.

## 11. Monitoring with Metrics and Alerts

Collect the following metrics if exposed by your version and instrumentation:

- Renewals received in the last minute.
- Expected renewals and renewal threshold.
- Self-preservation state.
- Registered instance count by application and status.
- Eviction counts and eviction timestamps.
- Renewal request success, error, and timeout rates.
- Registry API latency and peer replication latency.
- Consumer registry fetch latency and cache age.
- Server CPU, heap, GC pauses, and thread/connection pools.

Exact metric names vary across Spring Boot Actuator, Micrometer, Spring Cloud Netflix, and Eureka versions. Do not assume a single metric name exists in every release; inspect exposed metrics and verify tags/aggregations before creating alerts.

Useful alerts should distinguish:

| Alert | Meaning |
|---|---|
| Prolonged active self-preservation | Renewals stayed below threshold for an extended period |
| Elevated renewal error rate | Clients or server are losing heartbeat requests |
| Sudden drop in registered instances | Potential outage, deployment, or mass eviction |
| Registry peer divergence | Servers do not share the same state |
| Stale instance selection | Consumers still send requests to confirmed dead instances |
| High fetch latency/cache age | Consumers are slow to receive registry updates |

Do not alert only on self-preservation being active. Combine renewal error rates and stale requests to tell whether protection is retaining dangerous records.

## 12. Quick Diagnostic Table

| Symptom | Where to focus | Remediation direction |
|---|---|---|
| Self-preservation active, all clients fail renewals | Network, proxy, Eureka Server | Check routing, server health, peers, and TLS |
| Only one provider fails renewals | Client config/runtime | Check URL, DNS, resources, logs, and credentials |
| Renewals recover, yet stale records remain | Eviction/lease/server state | Check self-preservation, leases, and eviction cycle |
| Server deleted instance, yet consumer still calls it | Client fetch/cache/LoadBalancer | Check fetch interval and cache propagation |
| Healthy instance mistakenly evicted | Threshold/lease/network stability | Inspect renewal bursts, GC pauses, packet loss, and lease timeouts |
| Self-preservation activates after scale-down | Threshold update/topology change | Compare actual instance count and threshold update timing |
| Eureka peers show different data | Peer replication/network | Check peer URLs, connectivity, and replication logs |
| Client receives 401/403 or TLS error | Security layer | Check auth, truststore, certificates, and proxy |

## 13. Post-Incident Checklist

1. Confirm which providers are alive and which have stopped.
2. Record self-preservation state and renewal threshold.
3. Compare actual renewals against expected instance count.
4. Verify clients register and renew with the right Eureka Server.
5. Check DNS, network, proxy, TLS, and authentication.
6. Verify lease expiration and eviction intervals are reasonable.
7. Check state across all Eureka peers.
8. Check consumer fetch intervals and caches.
9. Delete stale registrations only after confirming the instance is no longer running.
10. Verify LoadBalancer stops selecting failing endpoints.
11. Monitor stable renewals across multiple intervals.
12. Document root cause, configuration changes, and before/after measurements.

## 14. Principles to Remember

- Self-preservation is a mechanism protecting the registry when actual renewals fall below the expected threshold.
- When active, stale instances may linger because eviction is restricted.
- Self-preservation is usually a consequence of reduced renewals, not necessarily the cause of renewal failures.
- Separate issues across client, network, proxy, server, peer replication, and consumer cache.
- Estimate renewal thresholds from instance counts and send intervals, yet verify against live dashboard/metrics.
- Do not shorten leases or disable self-preservation solely to silence warnings.
- Confirm an instance is truly dead before deregistering or deleting its registration.
- After renewals recover, still verify that both the registry and consumers have converged.

When Eureka enables self-preservation or continuously fails renewals, start by locating where heartbeats are being lost. Then inspect thresholds, leases, eviction, and caches layer by layer. Restore renewals for live providers, verify stale records before cleanup, and re-measure requests from consumers. This evidence-driven approach preserves healthy instances during network issues while safely removing dead endpoints.

## References

- [Spring Cloud Netflix 5.1.0 — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Netflix Eureka — Server Self Preservation Mode](https://github.com/Netflix/eureka/wiki/Server-Self-Preservation-Mode)
- [Netflix Eureka — Understanding Client/Server Communication](https://github.com/Netflix/eureka/wiki/Understanding-eureka-client-server-communication)
- [Netflix Eureka — Peer-to-Peer Communication and Self-Preservation](https://github.com/Netflix/eureka/wiki/Understanding-Eureka-Peer-to-Peer-Communication)
- [Netflix Eureka — PeerAwareInstanceRegistryImpl source](https://github.com/Netflix/eureka/blob/master/eureka-core/src/main/java/com/netflix/eureka/registry/PeerAwareInstanceRegistryImpl.java)
- [Netflix Eureka — AbstractInstanceRegistry source](https://github.com/Netflix/eureka/blob/master/eureka-core/src/main/java/com/netflix/eureka/registry/AbstractInstanceRegistry.java)

# Lease Expiration Duration and Heartbeat Renewal Interval

## 1. What Problems Do Heartbeat and Lease Solve?

In Spring Cloud Service Discovery, Eureka needs to know which instances can still receive requests. When an application starts up, Eureka Client registers the instance with Eureka Server. Afterward, the client sends periodic heartbeats to indicate that the instance is still active. With each successful heartbeat, the server renews the instance's lease in the registry.

These two concepts are closely related, though not identical:

- **Heartbeat:** a periodic message from Eureka Client to Eureka Server to renew the registration.
- **Lease:** the duration for which the server agrees to keep an instance if the next renewal has not arrived yet.

A heartbeat is the signal sent; a lease is the time limit the registry uses to evaluate whether a registration is still valid. If a client stops abruptly or loses connectivity, the server will not receive heartbeats and the lease can expire.

For example, a payment instance registers with Eureka. As long as the instance runs normally, it continuously renews its lease. If the process is killed or the host loses network connectivity, heartbeats stop. After the configured wait period, Eureka can remove that instance from the registry so other clients stop selecting it.

## 2. Lifecycle of Heartbeat and Lease

An instance typically goes through the following steps:

1. **Register:** Eureka Client sends instance information such as application name, hostname, IP, port, and status to Eureka Server.
2. **Renew:** the client sends periodic heartbeats to renew the lease.
3. **Expire:** if the server receives no heartbeat within the lease duration, the registration is considered expired.
4. **Evict:** Eureka Server's eviction task checks expired leases and removes instances from the registry, unless the self-preservation mechanism blocks eviction.
5. **Cancel:** if the application shuts down gracefully and sends a deregistration request, the server can remove the instance without waiting for the lease to expire.

~~~mermaid
stateDiagram-v2
    [*] --> Registered: Register
    Registered --> Registered: Heartbeat / Renew
    Registered --> Expired: No renewal received before lease expiration
    Expired --> Evicted: Eviction task permits removal
    Registered --> Cancelled: Cancel on graceful shutdown
    Evicted --> [*]
    Cancelled --> [*]
~~~

The key point is that **lease expiration does not mean the instance disappears from the registry at that exact second**. The server still has to run the eviction task, and self-preservation may pause instance removal. In addition, Eureka Clients using a registry cache may take time to receive the updated list.

## 3. Common Default Intervals

With the common Eureka configuration in Spring Cloud Netflix, two default values are typically used:

| Property | Common Default Value | Meaning |
|---|---:|---|
| **eureka.instance.lease-renewal-interval-in-seconds** | 30 seconds | Interval between two heartbeats sent by the client |
| **eureka.instance.lease-expiration-duration-in-seconds** | 90 seconds | Time the server waits since the last renewal before the lease expires |

With a 30-second heartbeat and a 90-second lease, the server allows an instance to miss a couple of heartbeats before considering the lease expired. This setting helps avoid removing an instance solely due to a briefly delayed heartbeat.

These two values are common defaults, not mandatory constants. They can vary depending on library version and deployment configuration. In operations, check the effective configuration of both the application and Eureka Server rather than relying only on default values remembered from another version.

### 3.1. Example of Calculating Lease Expiration Time

Suppose the server receives the latest heartbeat at 10:00:00 and the lease duration is 90 seconds:

| Time | Event |
|---|---|
| 10:00:00 | Server receives heartbeat and renews lease |
| 10:00:30 | Client is expected to send the next heartbeat |
| 10:01:00 | Client is expected to send the next heartbeat |
| 10:01:30 | 90 seconds have elapsed since the last renewal; the lease can be considered expired |
| After 10:01:30 | Eviction task checks and may remove the instance |

This is an illustrative example with ideal timestamps. Actual timing depends on request send/receive times, network latency, task scheduling, and self-preservation state.

## 4. Distinguishing Expiration Time from Eviction Time

Eureka Server does not necessarily remove an instance the instant the clock passes the lease duration. The server has a periodic task to check and evict expired leases. The property commonly used to adjust this task's interval is:

| Property | Common Default Value | Role |
|---|---:|---|
| **eureka.server.eviction-interval-timer-in-ms** | 60000 ms | Interval between eviction task runs |

For example, if a lease expires at 10:01:30 and the eviction task runs every 60 seconds, the instance may be removed on the next check. Therefore, the time from the last heartbeat until the instance is removed can be longer than 90 seconds.

The total time can be visualized as follows:

~~~text
Last renewal
    |
    |<------ lease duration ------>|
    |                              |
    v                              v
 10:00:00                      10:01:30
                                  |
                                  | Wait for next eviction run
                                  v
                             Instance removed
~~~

Do not rely solely on lease duration to guarantee failure-detection time for business operations. If the system needs to stop sending requests to a failing instance faster, combine health checks, timeouts, and retry policies on the service-calling side.

## 5. Configuring Heartbeat and Lease in Spring Cloud

The following properties are typically placed in the configuration file of each application registering with Eureka:

~~~yaml
spring:
  application:
    name: payment-service

eureka:
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
~~~

In this configuration:

- **lease-renewal-interval-in-seconds** specifies the instance's heartbeat interval.
- **lease-expiration-duration-in-seconds** specifies the lease duration that the instance advertises to Eureka.
- **service-url.defaultZone** specifies the Eureka Server endpoint the client uses.

To tune eviction, configure the property on Eureka Server:

~~~yaml
eureka:
  server:
    eviction-interval-timer-in-ms: 60000
~~~

If there are multiple Eureka Servers, ensure appropriate configuration and connectivity between peers. One node removing an instance from its local registry still needs time for updates to propagate to peers or client caches.

### 5.1. Choosing Heartbeat and Lease Intervals

When tuning, balance the speed of detecting failed instances against tolerance for network latency:

- Overly frequent heartbeats increase periodic request load on Eureka Server, especially with many instances.
- Overly infrequent heartbeats delay liveness signals reaching the registry.
- An overly short lease can cause healthy instances to be marked expired during long JVM pauses, CPU saturation, or flaky networking.
- An overly long lease keeps dead instances visible in the registry for longer.

A practical rule of thumb is that lease duration should be several times larger than the heartbeat interval to provide a buffer for delayed or temporarily failed heartbeats. The common default of 90 seconds and 30 seconds represents a 3:1 ratio. This is a starting point, not a ratio suitable for every system.

For example, for an application with long GC pauses or running across a network with variable latency, a 90-second lease may be too short. Conversely, a system requiring rapid removal of failed instances must carefully evaluate reducing the lease, because reducing it too aggressively can cause false evictions.

## 6. How Does Self-Preservation Affect Eviction?

Eureka Server has a **self-preservation** mechanism to curb mass instance eviction when the number of received heartbeats drops abnormally low. A network outage can prevent many healthy instances from sending heartbeats simultaneously. If the server removed every expired lease at that moment, the registry could lose large numbers of instances that are still running.

When self-preservation is triggered, Eureka can pause eviction to preserve the registry. This reduces the risk of mistakenly removing instances during a network incident, but also has a trade-off: instances that have genuinely died may remain in the registry longer.

A common property for enabling/disabling this mechanism on the server is:

~~~yaml
eureka:
  server:
    enable-self-preservation: true
~~~

The value **true** is typically the default in Eureka Server. Do not disable self-preservation just so the dashboard removes instances faster. Before changing it, understand your actual heartbeat rate, network quality, instance count, and how applications handle stale instances.

### 6.1. Example When Many Heartbeats Are Lost Together

Suppose there are 100 instances and each instance sends a heartbeat every 30 seconds. Under normal conditions, the server expects roughly 200 heartbeats per minute. If a network incident causes the server to receive only a small fraction of those heartbeats, the server may judge the renewal rate abnormally low and trigger self-preservation.

In this situation:

- Some instances may actually have stopped.
- Other instances are still healthy, but their heartbeats cannot reach the server.
- If all overdue instances were removed, the server could mistakenly evict living instances.
- Self-preservation prioritizes keeping the registry intact during an abnormal period; therefore, the registry may contain stale data.

The figure of 200 heartbeats per minute is simply an illustrative calculation of 100 instances multiplied by 2 times per minute. Actual renewal rates also depend on the number of registered instances, effective configuration, and observation window.

## 7. What Happens in Operational Scenarios?

### 7.1. Graceful Instance Shutdown

When an application shuts down properly, Eureka Client can send a cancel request to deregister. Upon receiving cancel, the server removes the instance from the registry and replicates the change according to the cluster's mechanism. This avoids waiting for the lease to expire.

However, if the process is forcefully killed, the VM is powered off abruptly, or the container loses connectivity before sending cancel, the server does not receive a shutdown notice. Detection then depends on heartbeats, lease expiration, and eviction.

### 7.2. Instance Still Running but Loses Connection to Eureka

Suppose `payment-service` is still processing internal requests but cannot connect to Eureka Server. The client cannot renew its lease. Once the lease expires and the server runs eviction, the instance can be removed from the registry even though the process is still running.

This is an example of false eviction: the registry judges the instance unavailable due to missing heartbeats, while the business process is still alive. When connectivity is restored, Eureka Client can re-register the instance; how quickly peers and other clients see the instance depends on the registry update process.

### 7.3. Eureka Server Disruption

If a Eureka Server stops temporarily, clients cannot send heartbeats to that node. In a multi-node cluster, clients can continue communicating with another peer if multiple endpoints are configured and the network still permits connections. Registries across nodes may temporarily differ.

When the server recovers, monitor peer connections, re-registration, and registry updates. Do not assume every client cache is updated the instant the server finishes starting up.

### 7.4. JVM Pause or Host Overload

A long JVM pause, stop-the-world GC, CPU starvation, or a blocked thread pool can delay heartbeats. If the lease is configured too close to the heartbeat interval, the server may consider the instance expired even though the process will resume once the pause ends.

Therefore, when investigating unexpected instance evictions, inspect GC logs, CPU, threads, network, and Eureka logs together. Simply increasing the lease without finding the cause of the stall can mask real performance problems.

## 8. Monitoring Heartbeats and Diagnosing Lease Expiration

When an instance disappears from the registry, determine whether it was intentionally cancelled or evicted due to missing heartbeats. A practical diagnostic procedure can include:

1. Check application logs for Eureka connection errors, timeouts, or heartbeat sending failures.
2. Check Eureka Server logs for renewal, lease expiration, eviction, and self-preservation information.
3. Compare the last heartbeat timestamp against the effective lease duration.
4. Check the eviction interval and whether self-preservation is blocking eviction.
5. Inspect GC pauses, CPU, thread pools, DNS, firewalls, and network latency on both client and server sides.
6. Compare registries across Eureka Servers and client-side caches to distinguish registration errors from update latency.

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Instance disappears while app is still running | Delayed heartbeats or lost connection | Client logs, network, GC, lease duration |
| Dead instance remains visible for a long time | Long lease, slow eviction runs, or self-preservation | Server logs, eviction interval, renewal rate |
| Many instances become stale at once | Network incident or overloaded Eureka Server | Peer connectivity, overall heartbeats, CPU, and threads |
| Instance reappears after some time | Client reconnected and re-registered | Register/renew logs and network recovery timestamp |
| Nodes show different instance counts | Replication or caches have not converged | Peer logs, per-node registry, cache fetch timing |

The dashboard is useful for observing the registry, but it does not replace logs and metrics. Check from multiple nodes and from the client side to determine the state the application is actually using.

## 9. Common Configuration Mistakes

### 9.1. Setting the Lease Smaller Than or Too Close to the Heartbeat Interval

If the lease barely equals the heartbeat interval, a single delayed request can cause the lease to expire before the next renewal reaches the server. Leave a large enough buffer for network latency, thread scheduling, and JVM pause times.

### 9.2. Only Increasing the Lease to Hide Heartbeat Failures

A longer lease reduces false evictions, but also extends the time dead instances remain in the registry. If heartbeats are failing due to DNS, firewall rules, or server overload, fix the root cause instead of only extending the duration.

### 9.3. Confusing Eviction Interval with Lease Duration

Lease duration is the wait time since the last renewal. Eviction interval is how often the server checks for expired leases. The two parameters control different steps; changing one does not substitute for the other.

### 9.4. Disabling Self-Preservation in Production

Disabling self-preservation can make the server remove instances faster when heartbeats drop, but during a network partition it can mistakenly remove many active instances. Only change this mechanism after clearly assessing the risks and having appropriate health checks, observability, and recovery policies in place.

### 9.5. Assuming an Evicted Instance Is Immediately Known to All Clients

Eureka Clients may hold a registry cache and refresh periodically. After server eviction, another client can still see the old instance for a period of time. Calling applications still need timeouts, bounded retries, and connection error handling.

## 10. Example Configuration Choices by Goal

No single set of values fits every system. The following table outlines how to think about tuning:

| Goal | Tuning Direction | Trade-off to Accept |
|---|---|---|
| Reduce heartbeat load with very many instances | Increase heartbeat interval | Slower detection of failed instances |
| Detect failures faster | Decrease lease duration and re-evaluate eviction interval | Higher risk of false eviction during network or JVM delays |
| Tolerate unstable networks | Increase lease buffer and keep self-preservation | Dead instances may remain in the registry longer |
| Avoid stale registry after network outage | Monitor peers, caches, renewals, and health checks | Requires additional metrics and operational procedures |

For example, an internal system with a stable network and moderate instance count might start with a 30-second heartbeat and 90-second lease. A system spanning multiple network zones needs to measure actual latency, JVM pause times, and delayed heartbeat rates before choosing a lease. After making changes, test by stopping an instance, briefly blocking connectivity to Eureka, and restoring the network to observe the entire lifecycle.

## 11. Summary

A heartbeat is the liveness signal Eureka Client sends to renew its lease. The lease defines how long the server waits after the last renewal before a registration can expire. In common configurations, the default heartbeat is typically 30 seconds and the lease duration is typically 90 seconds.

Lease expiration, eviction, and clients seeing the updated registry are distinct milestones. The eviction task runs periodically, self-preservation can delay removal, and client-side caches may update afterward. When tuning heartbeats or leases, balance failure-detection speed, load on Eureka, and tolerance for network delays or JVM pauses. Monitoring renewals along with expiration, eviction, and self-preservation logs helps distinguish genuinely dead instances from healthy ones temporarily unable to send heartbeats.

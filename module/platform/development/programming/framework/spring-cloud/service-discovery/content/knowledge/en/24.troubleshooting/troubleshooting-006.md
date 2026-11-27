# Stopped Instance Still Appears in Discovery Results

## Objectives

After this lesson, you will be able to:

- Distinguish a registration still present in the registry from stale data in the consumer's cache.
- Identify why a stopped instance is still returned via Eureka, Consul, ZooKeeper, or Kubernetes.
- Understand cleanup timing across leases, health checks, session timeouts, and Pod termination.
- Inspect status at the source registry, client cache, LoadBalancer, and DNS.
- Clean up stale instances without accidentally deleting a running replica.
- Design graceful shutdown, health checks, timeouts, and monitoring to minimize stale discovery windows.

## 1. A Stopped Instance Does Not Necessarily Disappear Immediately from Discovery

When a process stops, multiple components may still retain information about that instance:

1. **Process:** the application exited or the container stopped.
2. **Provider registration:** the instance's registration record remains in the registry.
3. **Registry view:** the registry server or agent still returns that record.
4. **Consumer cache:** DiscoveryClient or the discovery library still caches the old instance list.
5. **Load balancer / DNS cache:** the routing layer still holds the previously resolved endpoint or address.

Therefore, pinpoint exactly which layer holds stale data. If the registry has already deleted the registration yet the consumer still returns the instance, deleting records on the server again will not fix the cache. Conversely, if the source registry still returns the instance, refreshing the consumer cache only reloads the same record.

### Distinguishing Five States

| State | Meaning | How to verify |
| --- | --- | --- |
| Process stopped | JVM/container is no longer running. | Process table, container runtime, Pod/container status. |
| Endpoint unreachable | Address/port is no longer serving connections. | Connect directly to host and port; observe timeout/refused. |
| Registration stale | Registry still keeps the instance even though process stopped. | Query the registry server/agent directly. |
| Health not passing | Instance still has a registration, but health check reports failure. | Inspect check status and output. |
| Consumer cache stale | Source registry updated, but consumer still holds old endpoint. | Compare registry API against DiscoveryClient output on consumer. |

Do not conclude a registration is broken simply because a request to an endpoint failed. The process may have stopped while its lease has not yet expired; or the registry may already be clean while the consumer has not refreshed its cache.

## 2. Common Causes

### 2.1. Abrupt Process Termination Without Deregistration

When an application shuts down normally, the framework usually gets a chance to send a deregister request. If the process is force-killed, a VM or node loses power, a network partition occurs, or the JVM crashes, shutdown hooks may not run. The registry must wait for lease, TTL, or session timeout before removing the registration.

### 2.2. Health Check Has Not Had Enough Time to Mark Failure

Health checks run periodically. If the check interval is 10 seconds and requires multiple consecutive failures, the instance may remain in a passing state for some time after the process stops.

Some registries only mark the instance critical; they do not automatically remove the registration as soon as a check fails. Removal may require separate cleanup configuration.

### 2.3. Registry Protects Data During Widespread Connectivity Loss

Eureka has self-preservation. When the heartbeat rate drops below an expected threshold, the server can pause eviction to avoid mass-deleting instances solely due to a network partition. In this situation, dead instances can remain in the registry.

### 2.4. Registry and Consumers Have Separate Caches

Eureka has a server response cache and a client registry cache. Consul has agent-local state and a cluster-wide catalog. ZooKeeper clients can maintain caches/watches. Spring Cloud LoadBalancer can also maintain its own cache. Each layer has its own update cycle.

### 2.5. Record Created Manually or Using Wrong Registration Type

A service may be registered via an agent config file, CLI, script, or external controller. If the process stops while the registration is persistent/static, the registry has no automatic signal to remove it.

In ZooKeeper, if a persistent znode is used instead of an ephemeral znode, the node will not disappear automatically when the session ends.

### 2.6. Duplicate Service ID or Instance ID

If multiple processes share the same instance ID, a deregister from an older process can affect a newer process's registration; or an older record can be mistaken for a live replica. Cross-check service ID, instance ID, host, port, node, and registration timestamp.

## 3. Diagnostic Workflow: Finding the Layer Holding the Stale Record

Always inspect from the source registry outward to the consumer, in order:

~~~~mermaid
flowchart TD
    A[Instance believed to be stopped] --> B[Check process/container/Pod]
    B --> C[Probe endpoint directly]
    C --> D[Query source registry]
    D --> E{Registry still returns instance?}
    E -- Yes --> F[Check lease, health check, session, or endpoint controller]
    E -- No --> G[Check DiscoveryClient cache]
    G --> H[Check LoadBalancer / DNS / service mesh cache]
    F --> I[Clean up the right instance and verify propagation]
    H --> J[Refresh cache via supported mechanism]
    I --> K[Consumer stops picking old endpoint]
    J --> K
~~~~

### Step 1: Verify the Instance Actually Stopped

Check the process, container, or Pod in the appropriate runtime. Cross-check both the IP and port advertised by the registry. If possible, call the endpoint directly to distinguish:

- **Connection refused:** host still responds, but no process is listening on that port.
- **Timeout:** host/network may be unreachable or a firewall is dropping traffic.
- **HTTP response:** the IP may have been reused by another process; verify service identity before concluding.

Do not rely solely on hostname. An IP can be reused by a new Pod or new machine.

### Step 2: Query the Source Registry

Use the registry's direct UI/API/CLI, avoiding relying only on consumer dashboards or logs. Record service ID, instance ID, address, port, health status, and metadata.

### Step 3: Compare with Consumer Results

On the consumer, record `DiscoveryClient.getInstances(serviceId)` output and the timestamp of the last refresh. If the registry already deleted the record yet the consumer still sees it, check:

- Registry fetch interval.
- Client-side cache or informer/watch.
- Spring Cloud LoadBalancer cache.
- Service mesh endpoint cache.
- DNS resolver and JVM DNS cache if using hostname/headless Service.

### Step 4: Clean Up Only After Identity Verification

Before deleting manually, verify that the instance ID/Pod UID/host-port genuinely belongs to the stopped process. If a new instance reused the same address or ID, manual deletion can mistakenly remove a healthy replica.

## 4. Eureka: Lease Expiration, Self-Preservation, and Cache

Eureka clients send heartbeats to renew their leases. Under common Spring Cloud Netflix defaults, a client renews roughly every 30 seconds and the server waits roughly 90 seconds from the last heartbeat before evicting the instance from the registry. These values can vary by version and effective configuration. Check **eureka.instance.lease-renewal-interval-in-seconds** and **eureka.instance.lease-expiration-duration-in-seconds**.

If the application shuts down normally, the Eureka client sends cancel/unregister. When the process is killed with `kill -9`, crashes, or loses connectivity before sending cancel, the server must wait for the lease to expire. Eviction still has to run afterward, and data must propagate through the response cache and client fetch cycle. [Spring Cloud Netflix properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html) describe leases and fetch intervals; Netflix docs also explain cancel, renew, and registry caches.

### Self-Preservation Can Retain Dead Instances

Eureka Server enables self-preservation by default in current configurations. When received heartbeats fall below the renewal threshold, the server can pause expiration/eviction to protect the registry from a widespread network partition. This can cause clients to keep receiving endpoints of instances that no longer exist. This is intentional protective behavior, not necessarily a bug in the eviction scheduler. [Netflix Eureka – Server Self Preservation](https://github.com/Netflix/eureka/wiki/Server-Self-Preservation-Mode).

When you see a stale instance:

1. Check the renewal count and renewal threshold.
2. Confirm whether the server is in self-preservation mode.
3. Check the network between client and Eureka server; heartbeats can be lost even while processes are alive.
4. Check whether instances send cancel during graceful shutdown.
5. Check the actual lease expiration and eviction intervals.
6. Check peer replication if different Eureka servers return differing registry views.

Do not disable self-preservation as a knee-jerk reaction. If the root cause is a network partition, disabling this mechanism can cause the registry to purge large numbers of healthy instances temporarily unable to send heartbeats.

### Registry Caches Prolong Staleness

Eureka has multiple cache layers:

- Server response cache updated periodically.
- Client periodic registry fetch, commonly defaulting to 30 seconds.
- Consumers can keep using stale caches when fetches fail.
- LoadBalancer can maintain its own cache on top of the Eureka client.

**eureka.client.filter-only-up-instances** defaults to true in current config properties, filtering out instances not in UP status. However, if the server still keeps a stale instance in UP status, this filter cannot know the process is dead.

Client configuration example:

~~~~yaml
eureka:
  client:
    registry-fetch-interval-seconds: 30
    filter-only-up-instances: true
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
~~~~

These are illustrative values matching common defaults, not a recommendation to change them arbitrarily. Shortening lease timeouts can cause healthy instances to be evicted during brief network blips or GC pauses. Align heartbeats, leases, eviction, and caches to your SLO after testing failure modes.

### Verification

You can query the Eureka REST API to inspect registration status on the server:

~~~~bash
curl -H "Accept: application/json" \
  http://eureka-server:8761/eureka/apps/INVENTORY-SERVICE
~~~~

Cross-check instanceId, hostName, ipAddr, port, status, and metadata. If the server no longer has the instance yet the consumer still returns it, focus on the client fetch cache and LoadBalancer cache. If the server still returns UP status, inspect lease/self-preservation and deregistration.

## 5. Consul: Health Checks, Critical Duration, and Agent/Catalog

Consul distinguishes between services registered on a local agent and the cluster-wide service catalog. The agent manages local services/checks and syncs state to the catalog. Anti-entropy periodically reconciles local agent state with the catalog. Therefore, determine which agent and catalog still hold the record. [Consul – Consistency](https://developer.hashicorp.com/consul/docs/concept/consistency).

### Critical Does Not Mean Deleted

When a health check transitions to critical, the service may still remain in the catalog. To have Consul automatically deregister a service after remaining critical for some duration, configure the check with **deregister_critical_service_after**. Consul only auto-removes it once the critical state persists for the configured duration; reap intervals may delay removal slightly further. [Consul – Health Check Configuration](https://developer.hashicorp.com/consul/docs/reference/service/health-check).

Service definition example:

~~~~yaml
service:
  name: inventory
  id: inventory-node-a-8080
  port: 8080
  checks:
    - name: inventory-http
      http: http://127.0.0.1:8080/actuator/health
      interval: 10s
      timeout: 2s
      deregister_critical_service_after: 5m
~~~~

5m is only an illustrative value. Choose a duration longer than normal recoverable glitches yet short enough not to retain dead endpoints too long. An HTTP/TCP/TTL check must genuinely monitor the process or serving capability; a check that only probes an intermediate open port may miss a broken application.

With TTL checks, the application/agent must update status before TTL expires. Without an update within the TTL, the check moves to critical. [Consul – TTL Checks](https://developer.hashicorp.com/consul/docs/register/health-check/vm).

### Comparing Agent and Catalog

Use the Health API to fetch instances along with check states:

~~~~bash
curl -s "http://consul-agent:8500/v1/health/service/inventory"
~~~~

Fetch passing instances only:

~~~~bash
curl -s "http://consul-agent:8500/v1/health/service/inventory?passing"
~~~~

Compare with the catalog:

~~~~bash
curl -s "http://consul-agent:8500/v1/catalog/service/inventory"
~~~~

If the service is in the catalog while checks are critical, it is a lingering registration that is unhealthy. If the service exists only on a local agent, inspect agent configuration, service definition files, and anti-entropy. If it has been removed from agent/catalog yet the consumer still sees it, inspect client caches or query consistency modes.

Services registered via CLI or agent configuration can persist across agent restarts if state/config is retained. Do not assume stopping the business process makes the Consul agent remove every service entry automatically. [Consul – Services Register](https://developer.hashicorp.com/consul/commands/services/register).

### Deregistering in the Right Place

When a service was registered via a local agent, prefer deregistering through that same agent so the agent updates the catalog:

~~~~bash
curl -X PUT \
  http://consul-agent:8500/v1/agent/service/deregister/inventory-node-a-8080
~~~~

Only do this after confirming the service ID no longer belongs to a live process. With Spring Cloud Consul, inspect lifecycle deregistration and health check configuration; do not delete catalog entries directly if the agent still treats the service as authoritative, because anti-entropy may re-register it.

## 6. ZooKeeper: Sessions and Ephemeral Znodes

Spring Cloud Zookeeper typically uses Curator to create registration nodes in ZooKeeper. If a registration is created as an ephemeral znode, the node exists for the lifetime of the session that created it. When the session ends or expires, ZooKeeper deletes the ephemeral node. [ZooKeeper Programmer's Guide – Ephemeral Nodes](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html).

### Why Does the Znode Remain After the Process Dies?

When the JVM crashes or a machine loses network connectivity, the client cannot send close session. The ZooKeeper server must wait until the negotiated session timeout expires. Losing a TCP connection does not equate to session expiration: the client can reconnect to the old session before timeout and keep the ephemeral znode alive.

Thus, staleness duration can approach the session timeout plus the time for consumers to receive watch events and refresh caches. Before session expiration, the node remaining visible is expected behavior under session semantics.

### Inspecting Znodes

Connect using the ZooKeeper CLI:

~~~~bash
zkCli.sh -server zk-1:2181
~~~~

List registrations:

~~~~text
ls /services/inventory
~~~~

Inspect metadata and stat of an instance:

~~~~text
get -s /services/inventory/inventory-node-a
~~~~

Check **ephemeralOwner** in stat:

- **ephemeralOwner non-zero:** the node belongs to a session and will be deleted when that session ends.
- **ephemeralOwner equal to 0:** the node is persistent; it will not auto-delete with the session.

If the node still exists after the session has expired, check whether the node is persistent, whether there is a path collision, or whether another client/session owns it. Do not manually delete the node before verifying ephemeralOwner and the associated session.

### Recovery and Caching

Once the session expires, the client must create a new session and re-create its registration. Consumer-side watchers/caches need to process the node deletion event or resync data. If the consumer relies solely on a local cache without handling reconnect/session state properly, discovery results may stay stale even after the znode is deleted.

Do not shorten the session timeout aggressively just to purge instances faster. Network jitter, GC pauses, or server failovers can expire healthy instances' sessions, causing registration churn.

## 7. Kubernetes: Pod Termination and EndpointSlice

In Kubernetes, distinguish Pod objects, container processes, Services, and EndpointSlices. When a Pod is deleted, the control plane marks the Pod as terminating and updates endpoint states. Endpoints representing terminating Pods are not immediately removed from EndpointSlice; the terminating state is published so consumers/load balancers can handle draining. Terminating endpoints have ready=false for backward compatibility. [Kubernetes – Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/).

EndpointSlice has three conditions:

- **ready:** shortcut for an endpoint that is serving and not terminating, except when publishNotReadyAddresses is set.
- **serving:** whether the endpoint is currently serving.
- **terminating:** whether the endpoint is in the process of terminating.

Service proxies normally skip terminating endpoints, though in some situations where all endpoints are terminating, proxies may continue selecting endpoints that are both serving and terminating to avoid dropping all traffic during a rolling update. [Kubernetes – EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

### Common Kubernetes Causes

1. **Pod is Terminating:** EndpointSlice still holds the endpoint during graceful shutdown.
2. **Container process died but Pod object remains:** controller has not deleted the Pod; inspect readiness/container state.
3. **Missing or misconfigured readiness probe:** Pod may be marked Ready even though the app is no longer serving properly.
4. **publishNotReadyAddresses: true:** Kubernetes treats endpoints as ready even when the Pod is not ready. This is often intentional for Headless Services used in StatefulSet peer discovery.
5. **Service without selector:** endpoints are managed externally; Kubernetes does not automatically edit the EndpointSlice for that Service.
6. **EndpointSlice managed by another controller:** a service mesh or custom controller may retain its own endpoints.
7. **DNS caching:** a headless Service can return Pod IPs; resolvers/clients may keep old addresses during TTL/cache windows.

### Inspecting Pod, Service, and EndpointSlice

~~~~bash
kubectl get pods -n commerce -o wide
kubectl describe pod inventory-7c8f9d9c7b-abcd1 -n commerce
kubectl get service inventory -n commerce -o yaml
kubectl get endpointslice -n commerce \
  -l kubernetes.io/service-name=inventory -o yaml
~~~~

Compare these fields:

- Pod metadata.deletionTimestamp, status.phase, status.containerStatuses.
- Service spec.selector and spec.publishNotReadyAddresses.
- EndpointSlice addresses, targetRef, conditions.ready, conditions.serving, conditions.terminating.
- Label endpointslice.kubernetes.io/managed-by to see which controller manages the slice.

If the Pod object was deleted yet the endpoint remains in an EndpointSlice managed by a custom controller, investigate that controller. If the EndpointSlice is clean yet the application still sees old IPs, check DNS caches, informers/watches, or LoadBalancer caches.

### ClusterIP vs. Headless Service Differences

With a ClusterIP Service, DNS returns a stable Service address. This address can still resolve even when no backend Pods remain. That does not mean an old Pod still exists in discovery; check the EndpointSlice for actual backends.

With a Headless Service (clusterIP: None), DNS can return individual Pod IPs. When Pods are deleted or endpoints change, resolvers or client DNS caches may retain old IPs for a while. Also check publishNotReadyAddresses, especially for StatefulSet peer discovery.

## 8. Consumer Cache and LoadBalancer Cache

If the source registry already deleted the instance yet the consumer still sees it, inspect each cache layer in order:

| Layer | Data that may remain stale | How to check |
| --- | --- | --- |
| Registry server response cache | Returned payload does not reflect latest change yet. | Compare direct API and cache update time. |
| DiscoveryClient | Locally stored instance list. | Check fetch interval, watch/reconnect, and last refresh time. |
| Spring Cloud LoadBalancer | Cached ServiceInstance list. | Check ServiceInstanceListSupplier, cache TTL, and version config. |
| Service mesh / proxy | Cluster endpoints from control plane. | Inspect endpoint/cluster dump and xDS update time. |
| DNS resolver | Stale A/AAAA/SRV records or Pod IPs. | Query DNS from consumer environment and check TTL. |
| JVM DNS cache | Hostname resolution cached inside JVM. | Check DNS cache policy and resolver in use. |

Do not restart all consumers immediately upon spotting a stale instance. First, identify which cache holds the old endpoint and whether it can refresh on its own. Mass restarts can spike load on the registry and cause instability if the registry is recovering.

With Eureka, current config properties specify eureka.client.registry-fetch-interval-seconds defaulting to 30 seconds; the server response cache also has its own update cycle. Clients only observe changes after data passes through these cycles. Do not treat a single fixed number as a propagation guarantee across all versions/topologies.

## 9. Graceful Shutdown to Avoid Stale Registrations

When an application stops normally, actively drain the instance out of traffic and deregister before the process vanishes.

Recommended sequence:

1. Transition readiness to REFUSING_TRAFFIC or equivalent state.
2. Stop accepting new requests and start draining in-flight requests.
3. Send deregistration/cancel to the registry if connectivity is still available.
4. Wait long enough for propagation so consumers/load balancers update.
5. Close the HTTP server, workers, and application connections.
6. Exit the process within the termination grace period.

With Spring Boot:

~~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~~

In Kubernetes, terminationGracePeriodSeconds must be long enough for the preStop hook, propagation, and shutdown phases. If the window is too short, kubelet may send SIGKILL before the app completes deregistration.

Graceful shutdown cannot protect against power loss, kill -9, node crashes, or network partitions. Leases, health checks, session timeouts, and readiness still must be tuned appropriately to handle non-graceful failures.

## 10. Handling by Registry

| Registry | When process stops abruptly | Priority action |
| --- | --- | --- |
| Eureka | Server waits for lease expiration; self-preservation may delay eviction. | Check heartbeats, self-preservation, eviction, response cache, and client fetch cache. |
| Consul | Health check turns critical; service may stay in catalog unless critical cleanup is configured. | Check local agent, health check, deregister_critical_service_after, and anti-entropy. |
| ZooKeeper | Ephemeral znode persists until session ends/expires. | Check session state, timeout, and ephemeralOwner. |
| Kubernetes | Pod terminating and endpoint propagation follow lifecycle/controller. | Check Pod deletion timestamp, readiness, EndpointSlice conditions, and selector. |
| DNS / Headless Service | DNS cache may still hold old Pod IP. | Check records, TTL, resolver, and JVM cache. |

Do not apply the exact same cleanup action across all registries. Manually deleting at one layer may be recreated by another agent/controller if the authoritative source still holds the record.

## 11. End-to-End Troubleshooting Workflow

When consumers keep calling a stopped instance, perform:

1. **Record identity:** service ID, instance ID, host/IP, port, namespace, Pod UID, or ZooKeeper path.
2. **Verify process:** is the process/container/Pod still running; exact stop timestamp.
3. **Probe endpoint directly:** distinguish connection refused, timeout, and a response from a new process.
4. **Query source registry:** inspect raw record, health, lease/session, and timestamps.
5. **If registry still holds record:** clean up per registry mechanism; inspect shutdown hooks, checks, leases, sessions, or controllers.
6. **If registry is already clean:** query DiscoveryClient on the consumer; identify which cache still holds the old endpoint.
7. **If LoadBalancer/DNS is still stale:** refresh cache via supported mechanism or wait for TTL; check resolver and service mesh.
8. **Verify no remaining traffic:** monitor request logs/metrics on the instance and consumer.
9. **Watch for recurrence:** find any process re-registering the old ID or controller recreating the endpoint.

### Completion Criteria

- Source registry no longer returns the stopped instance, or returns a status excluded by selection policy.
- Consumers stop picking the old endpoint after the measured propagation window.
- LoadBalancer and DNS no longer point to the old address if they publish endpoints directly.
- No unexpected re-registrations appear from agents/configs/controllers.
- Surviving replicas remain in the registry and continue serving traffic.

## 12. Recommended Metrics and Alerts

Track separately:

- Time from process stop until registration removal.
- Time from registry record removal until consumers stop returning the instance.
- Number of registrations with overdue heartbeats/renewals.
- Number of instances in critical, OUT_OF_SERVICE, terminating, or session LOST state.
- Failed deregistration count and cleanup retries.
- Age of discovery caches on consumers.
- Rate of requests to endpoints returning connection refused or timeout.
- Endpoint count in EndpointSlice vs. Ready Pod count.
- Unexpected persistent registration znodes if design requires ephemeral ones.

A useful metric is stale-selection rate: requests sent to instances verified as no longer alive divided by total routed requests. Combine this metric with deregistration and cache refresh timestamps to measure actual convergence time.

## 13. Testing Stale Instance Scenarios

| Experiment | What to observe |
| --- | --- |
| Graceful shutdown | Registry receives deregistration; consumer stops picking instance after propagation. |
| SIGKILL / process crash | Registry cleanup occurs via lease, check, or session timeout. |
| Network loss between provider and registry | Distinguish live process from lost heartbeats/sessions. |
| Widespread Eureka renewal drop | Whether self-preservation activates and stale leases are retained. |
| Consul health check critical | Whether service is deregistered after critical duration or stays in catalog. |
| ZooKeeper client disconnected longer than session timeout | Ephemeral znode is deleted and consumer receives watch/update. |
| Pod Terminating with preStop | EndpointSlice marks terminating/ready false; in-flight requests drain. |
| publishNotReadyAddresses enabled | Endpoints can be advertised ready even when Pod is not Ready. |
| Headless Service DNS cache | Whether resolver still returns deleted Pod IPs. |
| Consumer cache not refreshing | How long DiscoveryClient/LoadBalancer returns old instances after registry is clean. |

Record timestamps for milestones: process stopped, health failed, lease/session expired, registry record removed, client cache updated, and last request to stale endpoint. That allows separating registry cleanup time from consumer convergence time.

## 14. Prevention Checklist

- [ ] Instance ID is unique and stable within one process lifecycle.
- [ ] Graceful shutdown flips readiness to refuse traffic before deregistering.
- [ ] Shutdown hooks are not skipped in container/process lifecycle.
- [ ] Lease/heartbeat intervals tolerate network jitter and GC pauses.
- [ ] Eureka self-preservation is monitored; not disabled merely to force faster eviction.
- [ ] Consul has health checks genuinely testing the process/service and appropriate critical cleanup settings.
- [ ] ZooKeeper registrations use ephemeral znodes when session-based auto-deletion is required.
- [ ] Session timeout is neither too long nor too short for the failure model.
- [ ] Kubernetes has proper readiness probes and an adequate termination grace period.
- [ ] publishNotReadyAddresses is enabled only intentionally.
- [ ] Selectorless Services have an external EndpointSlice management process.
- [ ] DiscoveryClient, LoadBalancer, service mesh, and DNS cache TTLs/refreshes are clearly understood.
- [ ] Metrics exist for stale records, deregistration delay, and stale selection.
- [ ] Runbook compares source registry with consumer results prior to manual deletion.
- [ ] Both graceful shutdown and abrupt failures are tested.

## Key Takeaways

- A stopped process does not mean the registry record is deleted immediately.
- Always distinguish a stale registry from a stale consumer cache.
- Eureka has lease expiration and self-preservation; widespread heartbeat loss can cause the server to keep instances.
- Consul can retain services in critical state; auto-deregistration happens only when a critical duration is configured.
- ZooKeeper deletes ephemeral znodes when the session ends, not immediately on TCP disconnect.
- Kubernetes keeps terminating endpoints in EndpointSlice during Pod shutdown; publishNotReadyAddresses can cause unready endpoints to be treated as ready.
- Stable ClusterIP DNS does not prove backend Pods still exist; inspect EndpointSlice.
- Use graceful shutdown to deregister early, yet still configure lease/health/session cleanup for crashes and network partitions.
- Only delete manually after verifying the exact instance ID, Pod UID, or znode owner.
- Measure registry cleanup time separately from consumer cache convergence time.

## Official References

- [Spring Cloud Netflix – Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Netflix – Eureka Features](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Netflix Eureka – Server Self Preservation](https://github.com/Netflix/eureka/wiki/Server-Self-Preservation-Mode)
- [Netflix Eureka – Client/Server Communication](https://github.com/Netflix/eureka/wiki/Understanding-eureka-client-server-communication)
- [Consul – Health Check Configuration](https://developer.hashicorp.com/consul/docs/reference/service/health-check)
- [Consul – Agent Check API](https://developer.hashicorp.com/consul/api-docs/agent/check)
- [Consul – Service Registration and Deregistration](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [Consul – Consistency and Anti-Entropy](https://developer.hashicorp.com/consul/docs/concept/consistency)
- [Apache ZooKeeper – Programmer's Guide](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html)
- [Kubernetes – EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)
- [Kubernetes – Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes – Service API and publishNotReadyAddresses](https://kubernetes.io/docs/reference/kubernetes-api/core/service-v1/)

# Scaling Replicas Up or Down and Verifying Convergence

In microservices, increasing or decreasing the number of instances does not end with changing the replica count. After scaling, the deployment platform must create or stop processes; instances must pass readiness; the registry must receive registrations or deregistrations; data must propagate to discovery clients; LoadBalancer must update its candidate list; and traffic finally shifts to the new instance set.

These steps happen asynchronously and can have different latencies. Therefore, distinguish:

- **Desired replicas:** the replica count requested by an operator or autoscaler.
- **Running replicas:** the number of running processes/Pods.
- **Ready replicas:** the number of instances ready to accept requests.
- **Registered instances:** the number of instances with registrations in the registry.
- **Healthy instances:** the number of instances passing health checks per policy.
- **Discoverable instances:** the number of instances visible to consumers.
- **Serving instances:** the number of instances actually receiving and processing traffic.

A system is considered converged only when all relevant layers reflect the same desired state within an acceptable time bound. This lesson covers scale-out, scale-in, coordinating Kubernetes with Spring Cloud Discovery, handling Eureka/Consul, and measuring convergence time from the control plane to real traffic.

## 1. Lifecycle Model When Changing Replica Count

Suppose `inventory-service` currently has 3 instances and needs to scale up to 5. The orchestrator receives desired replicas = 5, creates additional workloads, waits for the application to become ready, and then instances register with the registry. Consumers must receive the updated list before LoadBalancer can pick the two additional instances.

When scaling down from 5 to 3, two instances must be pulled from traffic, complete in-flight requests, deregister from the registry, and stop their processes. If a process stops before consumers stop selecting the instance, requests can hit a dead endpoint.

~~~mermaid
flowchart TD
    DESIRED["Desired replicas change"] --> ORCH["Orchestrator / Deployment controller"]
    ORCH --> START["Create or stop processes / Pods"]
    START --> READY["Readiness and application health"]
    READY --> REG["Register / deregister in registry"]
    REG --> REPL["Registry replication / health evaluation"]
    REPL --> DISC["DiscoveryClient updates snapshot"]
    DISC --> LB["LoadBalancer updates candidates"]
    LB --> TRAFFIC["Traffic routes to new instance set"]
    TRAFFIC --> VERIFY["Verify counts and real requests"]
~~~

Each layer can converge at a different time. For instance, Kubernetes may already have enough Ready Pods while Eureka Client has not yet fetched the new registry; or Consul may already mark a service passing while a LoadBalancer cache still holds an old list.

### 1.1. States That Cannot Substitute for One Another

| State | Question | Common Source |
|---|---|---|
| Desired | How many replicas were requested? | Deployment, StatefulSet, HPA, or runtime config |
| Running | How many processes/Pods are running? | Orchestrator or process supervisor |
| Ready | How many instances are ready to receive traffic? | Readiness probe, Actuator readiness |
| Registered | How many registrations does the registry hold? | Eureka registry or Consul Catalog |
| Healthy | How many instances pass health checks? | Eureka status or Consul Health API |
| Discoverable | How many instances do consumers see? | `DiscoveryClient` |
| Eligible | How many instances can LoadBalancer pick? | `ServiceInstanceListSupplier` after filters |
| Serving | Which instances are actually receiving requests? | Access logs, request metrics, tracing |

Do not use Running Pod count in place of Healthy instance count. A process can be running without having opened its HTTP port, connected to the database, or finished initializing. Likewise, the registry may still retain the registration of a dead process until it receives deregistration or its lease expires.

## 2. Scale-Out: Increasing Replica Count

Scale-out typically involves the following steps:

1. An operator or autoscaler increases desired replicas.
2. The orchestrator creates new Pods/VMs/processes.
3. The application starts and completes initialization tasks.
4. Readiness transitions to passing.
5. The instance registers with Eureka or Consul.
6. The registry updates status and distributes the change.
7. Consumers receive the updated instance list.
8. LoadBalancer begins selecting the new instances.
9. Request metrics confirm the new instances actually receive traffic.

~~~mermaid
sequenceDiagram
    participant H as HPA / Operator
    participant K as Kubernetes
    participant A as New Spring Boot instance
    participant R as Eureka / Consul
    participant C as Consumer
    participant L as LoadBalancer

    H->>K: Set replicas = 5
    K->>A: Schedule and start Pod
    A->>A: Initialize application
    A->>A: Readiness becomes UP
    A->>R: Register service instance
    R-->>C: Registry data becomes available
    C->>R: Fetch / refresh registry
    C-->>L: Updated ServiceInstance list
    L->>A: Select new instance for request
    A-->>L: Successful response
~~~

### 2.1. Readiness Must Reflect Serving Capability

Readiness is the signal indicating whether an instance can accept requests. Do not mark Ready right when the JVM opens its port if the application is still:

- Running database migrations or warming up caches.
- Loading models or required datasets.
- Establishing connections to brokers or mandatory dependencies.
- Initializing clients and security configuration.
- Recovering state needed before processing requests.

With Spring Boot Actuator, you can use the readiness health group. For example:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
~~~

This is an illustrative example; include a dependency in readiness only if the service truly cannot serve when that dependency fails. If you put every optional dependency into readiness, an auxiliary outage can pull all instances out of traffic and cause a cascading failure.

The Kubernetes readiness probe can call the Actuator endpoint:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Kubernetes excludes unready Pods from EndpointSlices used for Service traffic. If the application also registers independently with Eureka or Consul, ensure registry status is synchronized according to the same readiness policy; Kubernetes readiness does not automatically update Eureka registration. The "Ready then register" order in the diagram is an operational goal to achieve, not an order automatically guaranteed by every integration. If a registry registers the instance before readiness passes, keep the instance in a non-serving status or let health checks exclude it from the candidate list until ready.

### 2.2. Startup Probes and Liveness Are Not Readiness

The three probe types serve distinct roles:

| Probe | Question | On Failure |
|---|---|---|
| Startup | Has the application finished starting up? | Kubernetes keeps retrying the startup probe; restarts only after exceeding the threshold |
| Liveness | Is the process alive and able to keep running? | Kubernetes restarts the container |
| Readiness | Can the instance accept requests right now? | Kubernetes removes the instance from Service endpoints |

Liveness should not check every external dependency. If a database temporarily loses connectivity and liveness fails, Kubernetes may restart instances en masse, increasing load on the database and remaining instances.

## 3. Scale-In: Safely Decreasing Replica Count

Scale-in is harder than scale-out because you must stop sending new requests to an instance about to stop while still finishing in-flight requests.

General flow:

1. Decrease desired replicas.
2. Orchestrator selects instances to terminate.
3. Instance transitions to terminating or not-ready state.
4. Endpoint routing and the registry stop including the instance in new lists.
5. Consumers refresh `DiscoveryClient` and LoadBalancer caches.
6. Application stops accepting new requests.
7. In-flight requests complete within the drain window.
8. Instance deregisters and process exits.

~~~mermaid
sequenceDiagram
    participant K as Orchestrator
    participant A as Instance to remove
    participant R as Registry
    participant C as Consumer
    participant L as LoadBalancer

    K->>A: Begin termination
    K->>A: Mark endpoint terminating / not-ready
    A->>R: Deregister or publish OUT_OF_SERVICE
    R-->>C: Updated registry state
    C->>C: Refresh discovery snapshot
    C-->>L: Remove instance from candidates
    Note over A,L: Wait for propagation and drain
    A->>A: Finish in-flight requests
    K->>A: Send TERM / close process
~~~

### 3.1. Pulling an Instance from Traffic Before Stopping the Process

If you merely send SIGTERM and wait for the application to exit, some consumers may still hold the instance in cache and pick it for new requests. Before stopping, there must be a mechanism signaling that the instance is no longer eligible for traffic:

- Kubernetes: Pod enters Terminating, readiness/EndpointSlice reflects that the endpoint is no longer Ready.
- Eureka: update status or deregister per lifecycle.
- Consul: deregister the service or make the health check transition to critical per designed procedure.
- External gateway or load balancer: remove the endpoint from the backend pool.

Removing an instance from discovery does not mean all in-flight requests have finished. You need a drain phase and an appropriate shutdown timeout.

### 3.2. Spring Boot Graceful Shutdown

Spring Boot supports graceful shutdown on embedded Tomcat, Jetty, and Reactor Netty. When the application context closes, the web server stops accepting new requests via its server-specific mechanism and gives in-flight requests time to complete.

You can configure it explicitly:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

The 30-second limit is only an example. Choose it based on p95/p99 request duration, background work, and the orchestrator's termination limit. If requests can run for 60 seconds while the shutdown timeout is only 10 seconds, requests may still be cut off.

Graceful shutdown handles only the web server and application lifecycle. It does not guarantee every registry, consumer cache, and gateway has updated before the process exits. Coordinate deregistration, readiness, and draining.

### 3.3. Kubernetes Termination and preStop

When a Pod is deleted, Kubernetes sets a deletion timestamp, marks the Pod Terminating, and begins shutdown. The control plane updates EndpointSlice while kubelet starts lifecycle shutdown on the node; these two happen in parallel, with no guarantee the hook waited for every proxy to finish updating. If `preStop` is configured, kubelet runs this hook before sending TERM; hook duration counts toward `terminationGracePeriodSeconds`.

Example:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: inventory
      image: example/inventory-service:1.0
      lifecycle:
        preStop:
          httpGet:
            path: /internal/drain
            port: 8080
            scheme: HTTP
~~~

Here, `/internal/drain` is an application-implemented endpoint to transition readiness or registry status. It does not exist out of the box in Spring Boot. The endpoint must be protected, allowing only kubelet/sidecar or internal mechanisms to call it. The HTTP hook should return success after recording the drain request; do not hold the request open for the entire drain duration.

Do not add a fixed `sleep` command without measuring convergence time. If a pause is needed for proxy or registry propagation, determine it experimentally and place it within the termination budget. The total of `preStop`, graceful shutdown, and drain must be less than the grace period; if exceeded, kubelet may forcefully stop the process.

### 3.4. Do Not Confuse Readiness with Deregistration

A Kubernetes readiness failure removes a Pod from EndpointSlice for Service traffic, but does not automatically delete the application's registration from Eureka or Consul. If the application registers into both systems simultaneously, there must be a separate lifecycle handling that registry.

With Eureka, the client can explicitly unregister on shutdown. With Consul, Spring Cloud Consul has registration and deregistration lifecycles; if using TTL heartbeats, handle stopping heartbeats and re-registration policies. Do not rely completely on lease/session timeouts when controlled scale-in is required.

## 4. Scaling in Kubernetes

A Kubernetes Deployment manages desired replicas via `.spec.replicas`. You can scale manually:

~~~bash
kubectl scale deployment inventory-service --replicas=5
~~~

Check status:

~~~bash
kubectl get deployment inventory-service
kubectl get replicasets -l app=inventory-service
kubectl get pods -l app=inventory-service
~~~

Fields commonly inspected:

- `spec.replicas`: desired replicas.
- `status.replicas`: Pods managed by the Deployment.
- `status.readyReplicas`: Ready Pods.
- `status.availableReplicas`: Pods considered available per `minReadySeconds`.

Example Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: inventory-service
  template:
    metadata:
      labels:
        app: inventory-service
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: inventory
          image: example/inventory-service:1.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
~~~

`maxSurge` allows temporarily creating extra Pods above desired replicas during a rolling update. `maxUnavailable` bounds how many Pods can be unavailable during an update. They govern rollouts, not autoscaling policies, and do not replace readiness.

### 4.1. Verifying EndpointSlice

For a Kubernetes Service, EndpointSlice reflects endpoints selected by the selector. Check:

~~~bash
kubectl get endpointslice -l kubernetes.io/service-name=inventory-service
kubectl get endpointslice -l kubernetes.io/service-name=inventory-service -o yaml
~~~

Inspect the conditions:

- `ready`: whether the endpoint is used for normal traffic.
- `serving`: whether the endpoint is actively serving requests.
- `terminating`: whether the endpoint is in the process of terminating.

A terminating endpoint usually has `ready=false`. In some situations where all endpoints are terminating, proxies may still use `serving` endpoints to avoid dropping all traffic. Therefore, when draining, inspect all three conditions, not just `ready`.

### 4.2. Autoscaling with HPA

Horizontal Pod Autoscaler adjusts desired replicas based on metrics such as CPU, memory, or custom/external metrics. Example:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: inventory-service
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: inventory-service
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
~~~

HPA updates desired replicas; the Deployment controller creates or deletes Pods. HPA reporting increased desired replicas does not mean instances are Ready or have appeared in the service registry.

Scale-in can use a stabilization window to avoid oscillation when metrics dip briefly. Choose min/max replicas, scaling policies, and stabilization based on load, startup duration, and service cost.

## 5. Scale-Out and Scale-In with Eureka

Eureka clients register metadata and send periodic heartbeats. Under current Spring Cloud Netflix configurations, common default values are:

| Property | Default | Meaning |
|---|---:|---|
| `eureka.instance.lease-renewal-interval-in-seconds` | 30s | Interval at which client sends heartbeats |
| `eureka.instance.lease-expiration-duration-in-seconds` | 90s | Time server waits for a heartbeat before treating lease as expired |
| `eureka.client.registry-fetch-interval-seconds` | 30s | Interval at which client fetches registry |
| `eureka.client.should-unregister-on-shutdown` | true | Client explicitly unregisters on shutdown |

Values depend on release and configuration. Do not set heartbeats/leases too low in production solely to shorten convergence time; network jitter can cause healthy instances to be considered lost.

### 5.1. Scale-Out with Eureka

When a new instance starts:

1. Eureka client creates a registration and sends it to the server.
2. Server stores instance metadata and initial status.
3. Client continues sending heartbeats.
4. Peer servers may need replication time.
5. Consumers fetch the registry and update local caches.
6. LoadBalancer uses the updated list.

Spring Cloud Netflix documentation notes that an instance may not be discoverable until the instance, server, and client have synchronized metadata in their caches; with default heartbeats, this process can take up to roughly three heartbeat periods. This describes convergence behavior, not a fixed SLA for every topology.

### 5.2. Scale-In with Eureka

When a Spring Boot client shuts down normally, `should-unregister-on-shutdown` (true by default) causes the client to ask the server to cancel the registration. On abrupt crashes or network loss, the server may delete the registration only after lease expiration and eviction occur.

Eureka server has self-preservation to avoid deleting instances en masse when receiving abnormally few heartbeats, as that may stem from a network partition rather than all services dying at once. When self-preservation is active, stale registrations can linger longer than expected. Do not disable self-preservation just to force faster registry deletion; first inspect renewal rates, networking, peer replication, and instance status.

Illustrative configuration:

~~~yaml
eureka:
  client:
    should-unregister-on-shutdown: true
    registry-fetch-interval-seconds: 30
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
~~~

When using Eureka with Spring Cloud LoadBalancer, remember that Eureka client already maintains a local registry cache. The LoadBalancer cache can add another layer of lag; if `DiscoveryClient` already caches, LoadBalancer documentation recommends considering disabling the LoadBalancer cache to avoid double caching.

## 6. Scale-Out and Scale-In with Consul

Spring Cloud Consul registers the service with host, port, ID, and metadata. By default, the integration creates an HTTP health check to `/actuator/health` and the Consul Agent checks it periodically. If the check fails, the instance is marked critical.

Example configuration:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        register: true
        health-check-path: /actuator/health
        health-check-interval: 10s
        register-health-check: true
~~~

During scale-out, a new registration can appear in the Catalog before its health check turns passing. Therefore, distinguish Catalog count from passing count. Consumers use the Health API and filter passing if they want only healthy instances.

### 6.1. HTTP Health Check and TTL Heartbeat

Consul has two common models:

- **HTTP check:** Agent actively calls the application's endpoint periodically.
- **TTL check:** Application actively sends heartbeats to the Consul Agent to renew its TTL.

A TTL heartbeat does not automatically mean the application is Ready. The application must send heartbeats only when health/readiness conditions are met. If a process keeps sending heartbeats even when its request handler cannot serve, Consul will keep an incorrect healthy status.

In Spring Cloud Consul, TTL heartbeats can be enabled via configuration:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        heartbeat:
          enabled: true
          ttl: 10s
~~~

Current Spring Cloud Consul documentation describes a default heartbeat interval of 30 seconds unless configured otherwise. Automatic re-registration when heartbeats fail is disabled by default; if enabled, understand re-register conditions and avoid creating unintended duplicate registrations.

### 6.2. Scale-In with Consul

On normal shutdown, the integration can deregister the service during lifecycle shutdown. On crashes or missed heartbeats, checks can transition to critical; registration does not necessarily vanish immediately. You can configure a critical duration before deregistration if your Consul version supports it and policy requires it.

Do not use `?passing` to count total registrations. That query returns only nodes with all checks passing. During scale-in, inspect both Catalog and Health APIs to tell whether an instance was deleted or is merely critical.

## 7. Interaction Between the Registry and Spring Cloud LoadBalancer

Even after the registry updates, consumers may not yet select the right new instance set because `DiscoveryClient` and LoadBalancer maintain separate caches.

Spring Cloud LoadBalancer uses `ServiceInstanceListSupplier` to fetch the instance list. The default cache has a 35-second TTL and capacity of 256 in current documentation. If a `DiscoveryClient` such as Eureka already caches, consider disabling the LoadBalancer cache to avoid double caching.

Example configuration when the registry client already caches:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

If `DiscoveryClient` does not cache, you can keep the LoadBalancer cache and choose a TTL aligned with convergence targets:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 10s
        capacity: 256
~~~

A 10-second TTL is only an example, not a universal recommendation. Lowering TTL makes updated lists visible faster but can increase discovery calls. Cross-check registry client refresh intervals, supplier caches, and filter policies.

### 7.1. Consumers Do Not Necessarily See Every Instance

LoadBalancer can filter instances by zone, hints, health, or metadata. Thus:

- Registry has 5 instances.
- `DiscoveryClient` has 5 instances.
- Supplier applies zone preference, leaving 3.
- Health filter leaves 2.
- LoadBalancer selects only from those 2 instances.

This is not necessarily a convergence failure. When verifying, compare the exact dataset at each layer.

## 8. Defining Convergence Time

Do not use a single "scaling done" concept. Define time milestones for scale-out and scale-in.

### 8.1. Scale-Out Convergence Time

Let:

- `t0`: timestamp when the request to increase desired replicas is sent.
- `t1`: timestamp when all new replicas reach Ready state.
- `t2`: timestamp when all new replicas are registered and healthy in the registry.
- `t3`: timestamp when target consumers see the new instances.
- `t4`: timestamp when LoadBalancer can select the new instances.
- `t5`: timestamp when successful requests are observed reaching the new instances.

Then:

~~~text
T_ready       = t1 - t0
T_registered  = t2 - t0
T_discovered  = t3 - t0
T_eligible    = t4 - t0
T_serving     = t5 - t0
~~~

Operational targets usually care about `T_serving`, because new instances are useful only once they actually receive and handle traffic. However, measuring each milestone identifies which layer causes delays.

### 8.2. Scale-In Convergence Time

Let:

- `s0`: timestamp when the request to decrease desired replicas is sent.
- `s1`: timestamp when the endpoint is marked terminating/not-ready.
- `s2`: timestamp when the registry stops considering the instance healthy or registration is deleted.
- `s3`: timestamp when consumers stop putting the instance in candidate lists.
- `s4`: timestamp when no new requests are sent to the instance.
- `s5`: timestamp when in-flight requests finish and the process stops.

~~~text
T_removed_from_candidates = s3 - s0
T_no_new_traffic           = s4 - s0
T_drain_complete           = s5 - s0
~~~

Scale-in is safe only when no new requests are sent to removed instances, and in-flight requests have enough time to complete before the process is stopped.

### 8.3. Setting Convergence SLOs

Internal SLO examples:

- 95% of scale-out operations take less than or equal to 90 seconds for new instances to receive successful requests.
- 99% of scale-in operations take less than or equal to 60 seconds for consumers to stop sending new requests to removed instances.
- 99% of in-flight requests finish within the termination grace period.

These numbers are only examples. Pick thresholds based on startup time, registry topology, cache TTLs, health-check intervals, request durations, and real load. Measure p50/p95/p99 across multiple scaling runs rather than relying on a single trial.

## 9. Metrics to Verify Convergence

You can build a custom metric set or aggregate from orchestrator, registry, and consumers:

| Metric | Type | Meaning |
|---|---|---|
| `service_replicas_desired` | Gauge | Desired replicas |
| `service_replicas_running` | Gauge | Running processes/Pods |
| `service_replicas_ready` | Gauge | Ready replicas |
| `service_registry_instances` | Gauge | Registrations by service/status |
| `service_discovery_instances` | Gauge | Instances visible to consumers |
| `service_loadbalancer_candidates` | Gauge | Candidates after filtering |
| `service_scale_operations_total` | Counter | Count of scale-out/scale-in operations |
| `service_scale_convergence_seconds` | Histogram | Time from scale request to convergence milestone |
| `service_instance_drain_duration_seconds` | Histogram | Instance drain duration |
| `service_registry_snapshot_timestamp_seconds` | Gauge | Timestamp of most recent registry snapshot |

Do not attach Pod UID or instance ID to every aggregate metric because of high cardinality. Use logs/events or tracing to investigate a specific scaling event.

### 9.1. PromQL Comparing Desired and Ready

~~~promql
service_replicas_desired - service_replicas_ready
~~~

A positive value indicates fewer Ready replicas than desired. Both metrics must share the same service/cluster labels so subtraction pairs matching series.

### 9.2. Gap Between Ready and Healthy Registrations

~~~promql
service_replicas_ready
-
sum by (service, cluster) (
  service_registry_instances{status=~"UP|passing"}
)
~~~

This query is accurate only if both metrics share the same scope, labels, and instance conventions. If registry gauges are scraped multiple times from multiple peers or datacenters, deduplicate or group properly before comparing.

### 9.3. Convergence Duration

With a custom histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(service_scale_convergence_seconds_bucket[30m])
  )
)
~~~

Define histogram observations consistently: for example, scale-out records an observation when new instances receive traffic, and scale-in records an observation when consumers no longer pick old instances. If combining both types, add an operation label with a bounded set of values.

## 10. Verification Procedure After Every Scale Operation

Use a fixed procedure instead of stopping when the orchestrator reports success.

### 10.1. Check Desired and Actual

With Kubernetes:

~~~bash
kubectl get deployment inventory-service
kubectl get pods -l app=inventory-service -o wide
kubectl rollout status deployment/inventory-service
~~~

Verify `desired`, `readyReplicas`, and `availableReplicas`. If a Pod is not Ready, check `kubectl describe pod` and container logs before investigating the registry.

### 10.2. Check Service Endpoints

~~~bash
kubectl get endpointslice -l kubernetes.io/service-name=inventory-service -o yaml
~~~

Verify new Pods have Ready endpoints. During scale-in, verify pulled Pods have terminating/not-ready conditions and are no longer used for normal traffic.

### 10.3. Check the Registry

Eureka:

- Find the service application and instance ID.
- Inspect host, port, and status.
- Verify new registrations appear or old registrations disappear.
- Check server peer replication and client fetch interval if peers/consumers diverge.

Consul:

- Query the Catalog to see if the registration still exists.
- Query the Health API to see passing, warning, or critical.
- Use `?passing` to check the set of instances passing all health checks.
- Verify datacenter, namespace, partition, and ACLs match across queries.

### 10.4. Check from Consumers

Call `DiscoveryClient.getInstances("inventory-service")` from the consumer itself or expose a protected internal diagnostic endpoint. Then inspect LoadBalancer's candidate list and the chosen instance IDs.

Do not check only from a single admin machine. DNS, ACLs, caches, zones, and network policies can cause different consumers to see different instance sets.

### 10.5. Check Real Traffic

Attach the instance ID to an internal response header or log/trace, for example:

~~~http
X-Served-By: inventory-7f8d9c
~~~

After scale-out, send enough requests to observe whether new instances receive traffic. After scale-in, confirm no new requests arrive at removed instances. Do not use a single isolated request to conclude round-robin is balancing evenly; algorithms, connection reuse, and request volume all affect observations.

## 11. Diagnostic Table When Convergence Fails to Complete

| Symptom | Layer to Inspect | Common Causes |
|---|---|---|
| Desired increases yet Running does not | Orchestrator/scheduler | Resource exhaustion, quotas, image pull, scheduling constraints |
| Running increases yet Ready does not | Application/readiness | Slow startup, failing dependency, wrong probe path |
| Ready increases yet registry count does not | Registration lifecycle | Auto-registration disabled, ACLs, wrong hostname/port, registry connection error |
| Registry has registration yet health is not passing | Health check | Wrong endpoint, network unreachable, app not ready |
| Registry is healthy yet consumers do not see instance | `DiscoveryClient` | Unrefreshed cache, wrong datacenter/namespace, ACLs, or peer lag |
| `DiscoveryClient` sees instance yet LoadBalancer does not select it | Supplier/filter | Stale cache, zone/hint/health filter, empty candidate list |
| Consumers pick new instance yet requests fail | Network/application | Wrong advertised address, port not open, TLS or dependency error |
| Scale-in finishes yet consumers still pick old instance | Deregistration/cache | Registry not yet deleted, stale discovery snapshot, LoadBalancer cache |
| Process stopped yet registration remains | Registry cleanup | Non-graceful shutdown, lease not expired, Consul critical entry not deregistered |
| Requests reset during scale-in | Drain/shutdown | TERM too early, short grace period, connection closed while request still running |
| Replicas oscillate continuously | Autoscaler | Noisy metrics, missing stabilization, unsuitable min/max or scaling policy |

## 12. Mistakes to Avoid

### 12.1. Checking Only Pod Running

Running does not mean Ready, Healthy, or Discoverable. Wait for full readiness conditions before considering scale-out complete.

### 12.2. Waiting Only for Registration to Appear

A registration can appear before health checks pass. Consumers may select the instance too early without proper filtering. Verify both status and successful traffic.

### 12.3. Using Lease Timeout as the Primary Scale-In Mechanism

Lease timeouts are designed to handle instances that lose heartbeats, not intentional draining. Normal shutdown should deregister or change status before the process exits.

### 12.4. Lowering Every Interval to Converge Faster

Lowering heartbeats, health-check intervals, registry fetch intervals, and cache TTLs simultaneously can raise load, trigger false positives, and complicate diagnosis. Adjust one layer at a time based on measurements and testing.

### 12.5. Forgetting Consumer-Side Caches

The registry may be accurate while `DiscoveryClient` or LoadBalancer caches still hold stale data. Inspect each layer and pick appropriate TTLs; avoid double caching when the registry client already caches.

### 12.6. Using `sleep` Instead of Verification

A fixed wait does not prove every consumer has updated. Inspect endpoints, candidate lists, and request metrics; use delays only as part of a measured shutdown budget.

## 13. Scaling Test Scenarios

Before production, test the following scenarios:

| Scenario | What to Verify |
|---|---|
| Scale 3 → 5 | Two new instances become Ready, registered, healthy, discoverable, and receive requests |
| Scale 5 → 3 | Two instances leave candidate lists, stop receiving new requests, and finish draining |
| Slow Pod startup | Unready instances receive no traffic |
| Temporary readiness DOWN | Endpoint is excluded from traffic per policy and restored when Ready |
| Graceful shutdown | Registration/endpoint is removed before the process stops |
| Abrupt kill | Leases/health checks clean up stale instances according to timeout |
| Registry disconnect | Consumers handle stale snapshots and recover per policy |
| Slow Eureka peer replication | Peers and consumers eventually converge on the same registry view |
| Slow or critical Consul check | Catalog and Health APIs reflect the difference accurately |
| LoadBalancer cache retains stale entry | Consumers stop picking the instance after refresh/expiry |
| Continuous autoscaler scale up/down | Stabilization limits replica flapping |
| Long requests during scale-in | Requests complete within the termination grace period |

Record timestamps for each milestone. Do not store only PASS/FAIL results; know how long it takes from a desired change to Ready, healthy in the registry, discoverable by consumers, and real traffic.

## 14. Operational Checklist

**Scale-out**

1. Check quotas and resources before increasing desired replicas.
2. Verify startup probe, readiness probe, and Actuator readiness.
3. Ensure registration is treated as eligible only when the instance can genuinely serve.
4. Check registry health and replication.
5. Inspect `DiscoveryClient` and LoadBalancer candidate lists.
6. Verify successful requests to new instances.

**Scale-in**

1. Choose the replica reduction count and identify instances being removed.
2. Mark instances terminating/not-ready or OUT_OF_SERVICE.
3. Stop selecting those instances for new requests.
4. Wait for discovery and load balancer convergence.
5. Drain in-flight requests.
6. Deregister and stop processes via graceful shutdown.
7. Verify the registry has no remaining stale registrations.

**Measuring convergence**

1. Record timestamp of desired replicas change.
2. Record timestamp when replicas become Ready.
3. Record timestamp when registry becomes healthy/removed.
4. Record timestamp when consumers see or stop seeing the instance.
5. Record timestamp of first successful request or last completed request.
6. Compute p50/p95/p99 and set appropriate SLOs.

## 15. Key Takeaways

- Scaling changes desired replicas; the registry only reflects registered instances and does not directly create processes.
- Scale-out must pass through startup, readiness, registration, registry propagation, discovery refresh, and LoadBalancer selection.
- Scale-in must pull instances from traffic, deregister, drain in-flight requests, and only then stop processes.
- Kubernetes readiness governs EndpointSlice but does not automatically sync Eureka or Consul registrations.
- Spring Boot graceful shutdown needs timeouts aligned with request durations and the termination grace period.
- Eureka heartbeats/leases, Consul health checks/TTLs, and LoadBalancer caches introduce distinct convergence milestones.
- Do not use lease expiration in place of graceful deregistration.
- Desired, Running, Ready, Registered, Healthy, Discoverable, Eligible, and Serving are distinct counts.
- Measure `T_serving` during scale-out and `T_no_new_traffic`/`T_drain_complete` during scale-in.
- Conclude scaling is complete only when counts and traffic across layers have converged within SLOs.

Scaling replicas up or down is a coordinated workflow spanning the orchestrator, application, registry, discovery client, and data plane. When every layer has explicit readiness, deregistration, and timeout boundaries, and is verified via timestamps and live traffic, the system can scale without routing requests to unready or stopped instances.

## References

- [Kubernetes — Deployments and Rolling Updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes — EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Cloud Netflix — Eureka Client Registration and Discovery](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Consul — Service Discovery and Health Checks](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Commons — LoadBalancer Caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)

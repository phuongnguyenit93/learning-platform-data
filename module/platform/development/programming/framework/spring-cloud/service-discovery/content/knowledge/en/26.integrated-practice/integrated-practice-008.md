# Performing a Rolling Update and Verifying Instances Stop Receiving Traffic

A rolling update gradually replaces instances of a service with a new version while the system continues serving requests. A successful rollout does not merely mean the new Pod turns Ready; you must verify that old instances stop receiving **new requests**, in-flight requests have time to complete, registries or Kubernetes Services do not keep selecting drained instances, and overall disruption stays within SLOs.

In Spring Cloud Service Discovery, consumers can locate instances via Eureka, Consul, ZooKeeper, or Kubernetes DiscoveryClient and then use Spring Cloud LoadBalancer to pick an endpoint. Therefore, during a rolling update, you must coordinate readiness, registration/deregistration, discovery caches, connection pools, and graceful shutdown. If you simply kill the process, consumers may keep choosing the stale address for a period of time.

This practice builds an observable rolling update workflow, inspects traffic flow before/during/after rollout, distinguishes Kubernetes Service from registry-based discovery, and performs a rollback when the new version fails readiness requirements.

## 1. Objectives and Completion Criteria

After this practice, you will be able to:

- Configure a Deployment rolling update so new instances are Ready before old instances are removed.
- Use readiness probes to stop routing new traffic to draining instances in Kubernetes Service endpoints.
- Combine Spring Boot graceful shutdown with a drain phase to finish in-flight requests.
- Understand the differences among Pod readiness, Eureka status, Consul health, and consumer registry caches.
- Observe instance ID/version in requests to identify which Pod receives traffic.
- Verify old instances receive no new requests once the drain converges.
- Verify in-flight requests complete or are bounded by shutdown timeout.
- Roll back the Deployment if the new version fails to become Ready or spikes errors.

A rollout is considered successful when:

1. Available instance count always meets minimum configured capacity.
2. New instances only receive traffic after passing readiness.
3. Old instances are marked to refuse new traffic before the process exits.
4. In-flight requests complete within the allowed graceful shutdown window.
5. Consumers stop selecting old instances once endpoints/registries/caches converge.
6. No 5xx errors or timeouts exceed SLO thresholds throughout the rollout.
7. Logs/metrics identify the exact version and instance handling each request.

## 2. Components Involved in the Draining Process

A rolling update spans multiple layers:

| Component | Responsibility During Rollout |
|---|---|
| Deployment controller | Creates new-version Pods and gradually scales down old-version Pods per maxSurge/maxUnavailable. |
| Readiness probe | Determines whether a Pod is eligible to receive new requests. |
| Kubernetes Service/EndpointSlice | Distributes traffic only to eligible endpoints; terminating endpoints are marked with dedicated conditions. |
| Spring Boot application | Switches readiness to REFUSING_TRAFFIC, stops accepting new requests, and completes in-flight requests. |
| Registry client | Updates status or deregisters the instance from Eureka/Consul/ZooKeeper per integration. |
| Consumer DiscoveryClient | Receives updated registry/endpoints and removes old instances from discovery view. |
| Spring Cloud LoadBalancer | Refreshes the cached instance list and selects valid endpoints. |
| Ingress/proxy/connection pool | Stops opening new connections to old backends and handles connection draining/keep-alive. |

These layers do not update simultaneously. Pod readiness may flip before consumer registry caches refresh. An external load balancer may need separate deregistration time. Thus, a Pod being Terminating and no new requests arriving at that instance are two distinct conditions.

## 3. Distinguishing Readiness, Liveness, and Graceful Shutdown

- **Readiness:** whether the Pod is ready to accept requests. When readiness fails, Kubernetes should exclude the Pod from normal serving endpoints.
- **Liveness:** whether the process is alive and should keep running. Liveness failure can cause kubelet to restart the container.
- **Startup probe:** gives the application enough time to start up before liveness/readiness are evaluated.
- **Graceful shutdown:** upon receiving SIGTERM, the server stops accepting new requests and waits for in-flight requests to complete within a configured window.
- **Drain:** the phase that notifies routing/discovery layers an instance is about to leave service and waits for that change to propagate.

Do not use liveness to represent draining state. If liveness fails, Kubernetes may restart the container mid-rollout, cutting off in-flight requests. Draining is normally represented by readiness transitioning to REFUSING_TRAFFIC.

## 4. Configuring Spring Boot for Readiness and Graceful Shutdown

Example application configuration:

```yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
```

Meaning:

- server.shutdown: graceful enables controlled shutdown of the embedded web server.
- spring.lifecycle.timeout-per-shutdown-phase: 30s sets the wait limit for one shutdown phase.
- management.endpoint.health.probes.enabled: true enables readiness and liveness health groups.
- /actuator/health/readiness is used as the readiness probe; /actuator/health/liveness is used as the liveness probe.

Graceful shutdown does not automatically replace readiness draining. It takes effect once the application receives the shutdown signal; readiness must change earlier so routing layers stop sending new requests while the server still has time to finish current requests.

### 4.1. Internal Endpoint to Switch Readiness to Refusing Traffic

A proactive approach is exposing an internal endpoint called only by the lifecycle hook. This endpoint publishes an AvailabilityChangeEvent so Spring Boot updates readiness state:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class DrainController {

    private final ApplicationContext applicationContext;

    DrainController(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    @PostMapping("/internal/drain")
    ResponseEntity<Void> drain() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.REFUSING_TRAFFIC
        );
        return ResponseEntity.accepted().build();
    }
}
```

When called, the readiness health group reflects the refusing-traffic state. Kubelet observes readiness failure and Kubernetes updates endpoint routing. This endpoint must be protected: allow calls only from lifecycle hooks over loopback/internal container or a dedicated administrative identity; never expose it externally.

If the application already has its own drain/readiness mechanism, reuse it instead of adding another endpoint. Verify that /actuator/health/readiness actually transitions to a non-success HTTP status after draining.

## 5. Configuring Kubernetes Service and Deployment

The Service uses a stable selector based on the application name. Do not put a version label in the Service selector if the goal is for one Service to serve both old and new Pods concurrently during rollout.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: payment-service
  namespace: commerce
spec:
  selector:
    app: payment-service
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
  namespace: commerce
spec:
  replicas: 3
  minReadySeconds: 10
  progressDeadlineSeconds: 600
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
        app.kubernetes.io/name: payment-service
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: payment
          image: registry.example.internal/payment-service:2.4.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: INSTANCE_ID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 3
            timeoutSeconds: 2
            failureThreshold: 1
          lifecycle:
            preStop:
              exec:
                command:
                  - /bin/sh
                  - -c
                  - "curl -fsS -X POST http://127.0.0.1:8080/internal/drain && sleep 10"
```

The configuration above illustrates a three-replica workload:

- maxSurge: 1 allows creating at most one extra Pod during rollout.
- maxUnavailable: 0 requires the Deployment to maintain the full desired count of available replicas during replacement, provided the cluster has resources to schedule the surge Pod.
- minReadySeconds: 10 requires a new Pod to stay Ready long enough before being counted as available.
- terminationGracePeriodSeconds: 60 allocates time for preStop and the shutdown process.
- preStop calls the internal drain endpoint, then waits 10 seconds for readiness/endpoint changes to propagate.
- Readiness probe checks traffic eligibility; liveness probe checks whether the process is still running.

The image must include /bin/sh and curl to run the preStop example. If the base image lacks those tools, package a suitable drain script or use a different lifecycle hook. The 10-second sleep is only an illustrative wait; measure convergence time of your cluster and ingress/load balancer to pick a realistic value.

preStop executes within the termination grace period and completes before kubelet sends the process termination signal. EndpointSlice updates and hook execution can occur nearly simultaneously; the wait gives routing time to update. It is not an absolute guarantee that every external client cache has received the change.

## 6. Understanding the Sequence When a Pod Is Replaced

When Deployment replaces an old Pod:

1. Deployment creates a new Pod.
2. The new Pod starts and passes startup/liveness probes.
3. The new Pod's readiness succeeds.
4. After minReadySeconds, Deployment can count the new Pod as available.
5. Deployment begins scaling down an old Pod per the rolling update strategy.
6. The old Pod enters Terminating state; Kubernetes updates EndpointSlice to reflect the terminating endpoint.
7. preStop calls the drain endpoint; the application flips readiness to REFUSING_TRAFFIC.
8. The hook waits for routing/health/discovery to update.
9. Kubelet sends SIGTERM once the hook finishes.
10. Spring Boot graceful shutdown stops accepting new requests and waits for in-flight requests to finish.
11. The process exits; if the grace period is exceeded, kubelet may send SIGKILL.

Exact synchronization between EndpointSlice updates, probes, and preStop should not be assumed instantaneous. Observe Pod conditions, EndpointSlice conditions, drain logs, and live requests to characterize your environment's timing.

terminationGracePeriodSeconds includes preStop runtime. In the example above, 10 seconds of draining plus up to 30 seconds of graceful shutdown fit inside the 60-second grace period, leaving headroom for hooks and process exit.

## 7. Tracking Instance ID and Version in Requests

To verify old Pods stop receiving requests, each response needs to identify its instance. You can create a test endpoint:

```java
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InstanceIdentityController {

    @Value("${INSTANCE_ID:local}")
    private String instanceId;

    @Value("${APP_VERSION:dev}")
    private String appVersion;

    @GetMapping("/test/identity")
    Map<String, String> identity() {
        return Map.of(
                "instanceId", instanceId,
                "version", appVersion
        );
    }
}
```

In production, you do not necessarily expose this endpoint to end users. You can include instance ID and version in structured logs, internal response headers, or controlled metric labels. Avoid putting unbounded Pod UIDs into metric labels if it causes high cardinality.

A useful request log contains:

- service.name
- service.instance.id
- service.version
- trace_id or correlation_id
- request received timestamp
- processing duration
- HTTP outcome

From this, you can identify the last request handled by an old instance and the first request handled by a new instance.

## 8. Step-by-Step Rolling Update Practice

### Step 1: Deploy the Initial Version

Deploy three replicas of version 2.4.0:

```bash
kubectl apply -f payment-service.yaml
kubectl rollout status deployment/payment-service -n commerce
kubectl get pods -n commerce -l app=payment-service -o wide
kubectl get endpointslices -n commerce \
  -l kubernetes.io/service-name=payment-service
```

Confirm all three Pods are Ready and EndpointSlice contains three serving endpoints. Record the Pod name, instance ID, and version of each Pod.

### Step 2: Generate Continuous Traffic

Run a consumer or load generator sending continuous requests to the Kubernetes Service:

```bash
while true; do
  date -u
  curl -fsS http://payment-service.commerce.svc.cluster.local/test/identity
  sleep 0.2
done
```

This example runs from a consumer Pod with DNS/network access to the Service. In real tests, log responses to categorize by instance ID/version while counting timeouts and HTTP error codes. If the consumer uses Spring Cloud LoadBalancer, send requests by service ID rather than calling ClusterIP DNS to test the actual deployed discovery path.

### Step 3: Start the Rolling Update

Switch the image to the new version, e.g., 2.5.0:

```bash
kubectl set image deployment/payment-service \
  payment=registry.example.internal/payment-service:2.5.0 \
  -n commerce

kubectl rollout status deployment/payment-service -n commerce
```

Watch Pods and EndpointSlices concurrently:

```bash
kubectl get pods -n commerce -l app=payment-service -w
kubectl get endpointslices -n commerce \
  -l kubernetes.io/service-name=payment-service -w
```

Observe that new Pods are counted available only after passing readiness and minReadySeconds. Old Pods are scaled down only once Deployment maintains sufficient availability under the strategy.

### Step 4: Verify Old Pods Stop Receiving New Requests

When an old Pod transitions to Terminating:

- Check logs showing /internal/drain was called successfully.
- Check /actuator/health/readiness transitions to unready.
- Inspect EndpointSlice: the old endpoint is marked terminating and is no longer ready for new traffic per Kubernetes semantics.
- Inspect request logs: the old instance receives no new requests after the drain converges.
- Check whether requests already in flight before draining completed within the shutdown timeout.

Commands to inspect Pods:

```bash
kubectl describe pod <old-pod-name> -n commerce
kubectl logs <old-pod-name> -n commerce --since=10m
kubectl get endpointslices -n commerce \
  -l kubernetes.io/service-name=payment-service -o yaml
```

EndpointSlices carry conditions such as ready, serving, and terminating depending on Kubernetes version. A terminating endpoint may still appear to support proxy/connection draining, yet must not be treated as a normal ready endpoint. Inspect the actual conditions rather than merely checking whether the IP address still appears in YAML.

### Step 5: Verify the New Version Serves Normally

After rollout:

```bash
kubectl rollout status deployment/payment-service -n commerce
kubectl get deployment payment-service -n commerce
kubectl get pods -n commerce -l app=payment-service -o wide
```

Send new requests and confirm the version is 2.5.0. Check error rates, latency, per-instance request counts, and provider logs. Do not rely solely on the Deployment's Available=True condition to conclude zero requests failed.

## 9. Adjusting for Eureka-Based Discovery

When providers register directly with Eureka, Kubernetes readiness does not automatically mean Eureka consumers immediately stop selecting the instance. Eureka has client-side registry caches and fetch intervals; Spring Cloud LoadBalancer can also cache the instance list separately.

A Eureka drain flow needs coordination:

1. Mark the instance OUT_OF_SERVICE before stopping traffic intake.
2. Wait for Eureka Server to receive the status update.
3. Wait for consumers to fetch the updated registry and refresh LoadBalancer caches.
4. Verify consumers no longer select the old instance.
5. Wait for in-flight requests to complete.
6. Close the application context so Eureka Client cancels its registration per lifecycle.
7. Exit the process within the shutdown grace period.

You can update status using ApplicationInfoManager in Spring Cloud Netflix:

```java
import com.netflix.appinfo.ApplicationInfoManager;
import com.netflix.appinfo.InstanceInfo;

@Component
class EurekaDrainService {

    private final ApplicationInfoManager applicationInfoManager;

    EurekaDrainService(ApplicationInfoManager applicationInfoManager) {
        this.applicationInfoManager = applicationInfoManager;
    }

    void markOutOfService() {
        applicationInfoManager.setInstanceStatus(
                InstanceInfo.InstanceStatus.OUT_OF_SERVICE
        );
    }
}
```

This is an example for a provider using Eureka Client. Verify your Spring Cloud Netflix version and system security/status propagation settings. Changing status does not guarantee all consumers drop the instance from cache immediately; wait and verify from actual consumers. You can combine this with readiness/traffic draining at ingress or Kubernetes to cut off network-layer traffic while Eureka propagation occurs.

Eureka heartbeats/leases and cancellation are registry lifecycle mechanisms. Graceful cancellation differs from abrupt process death waiting for lease expiration. Test both scenarios separately if failure detection verification is needed.

## 10. Adjusting for Consul-Based Discovery

With Consul, health checks can be configured to reflect readiness:

```yaml
spring:
  cloud:
    consul:
      discovery:
        register-health-check: true
        health-check-path: /actuator/health/readiness
        health-check-interval: 5s
        query-passing: true
```

When the drain endpoint switches readiness to REFUSING_TRAFFIC, the Consul agent observes the health check failing on its next interval. Consumers querying with query-passing=true can exclude non-passing instances from the list. However, check interval, timeout, catalog update, and LoadBalancer cache still introduce delay.

An appropriate sequence:

- Start readiness drain.
- Wait for Consul Health API to report the instance is no longer passing.
- Wait for consumer DiscoveryClient to stop returning the instance per query policy.
- Wait for LoadBalancer cache refresh.
- Complete in-flight requests and shut down the provider.
- Verify the service record is deregistered per shutdown/agent configuration.

A critical health check does not necessarily delete the service record from the Catalog. Distinguish "registered but not passing" from "deregistered." If deregisterCriticalServiceAfter is configured, deregistration timing and conditions must be accounted for separately.

## 11. Adjusting for Kubernetes DiscoveryClient and DNS

There are two common request paths:

### 11.1. Calling via ClusterIP DNS

The consumer calls http://payment-service.commerce.svc.cluster.local. The Kubernetes Service dataplane distributes traffic across ready endpoints. Readiness failure and terminating status in EndpointSlice help remove the old Pod from backend selection once updates propagate.

ClusterIP DNS names normally do not change when Pods are replaced. Consumers do not need to re-resolve DNS just because a Pod rolled out; changes primarily occur in EndpointSlice/dataplane.

### 11.2. Calling Pod Endpoints via DiscoveryClient

If Spring Cloud Kubernetes DiscoveryClient returns the Pod/endpoint list and Spring Cloud LoadBalancer selects directly, verify:

- Does the discovery client observe new endpoints?
- Are terminating/not-ready endpoints excluded from the list according to version and configuration?
- Has the LoadBalancer cache refreshed?
- Is the consumer holding open connections to old Pods?

If using a headless Service, DNS can return multiple Pod IPs directly. DNS resolvers and client caches can retain old IPs; TTLs and connection pools must be factored into the drain window.

Do not unintentionally combine client-side load balancing over Pod IPs with ClusterIP load balancing. Identify which layer selects the final Pod and inspect traffic at that layer.

## 12. Connection Draining and In-Flight Requests

Readiness only affects endpoint selection for new requests through the routing layer. It does not automatically close established TCP connections and does not automatically complete in-flight requests.

Distinguish:

- **New requests:** must be routed to other instances once drain converges.
- **In-flight requests:** need sufficient time to complete before the process stops.
- **Keep-alive connections:** may hold connections open to old instances; behavior depends on server, client, proxy, and connection pools.
- **Streaming/WebSocket/long polling:** may outlive default graceful shutdown durations; require dedicated policies.
- **Retries:** can shift requests to other instances but require idempotency to avoid duplicate business processing.

Spring Boot graceful shutdown helps the server stop accepting new requests per embedded server semantics and wait for active requests. However, wait time is bounded. Requests lasting longer than timeout-per-shutdown-phase can be interrupted when the process exits. Design business timeouts shorter than the shutdown budget or provide continuation/resume mechanisms.

If an Ingress, cloud load balancer, or service mesh is present, configure deregistration/drain delays at that layer. Proxy timings must align with terminationGracePeriodSeconds and the application's wait time for active requests.

## 13. Choosing Drain and Shutdown Timings

Total termination time must cover:

- preStop hook flipping readiness/status.
- Endpoint/registry propagation.
- Consumer cache refresh if using registry-based discovery.
- Connection draining at ingress/proxy.
- Completion of in-flight requests.
- Spring lifecycle shutdown and resource cleanup.

Example budget:

| Phase | Illustrative Duration |
|---|---:|
| Switch readiness to refusing traffic | 1 second |
| Wait for EndpointSlice/Consul/Eureka and proxy updates | 10–15 seconds |
| Wait for in-flight requests | 25 seconds |
| Close clients, connection pools, and resources | 5 seconds |
| Headroom | 10 seconds |
| Total | 51–56 seconds |

This is a budgeting example, not a universal default. For Eureka, fetch intervals may exceed 15 seconds; for Consul, health-check intervals and query behaviors vary; for Kubernetes Service, EndpointSlice propagation typically differs from registry caches. Measure actual p95/p99 and set a sufficiently large grace period.

Never set terminationGracePeriodSeconds smaller than preStop time plus shutdown timeout. Exceeding the grace period allows kubelet to force-kill the container and drop active requests.

## 14. Observability and Measurement During Rollout

Signals to monitor:

| Signal | Question to Answer |
|---|---|
| Pod Ready/NotReady | Are new instances ready? Have old instances stopped being considered ready? |
| EndpointSlice conditions | Is the old endpoint still ready? Is it marked terminating? |
| Registry status | Does Eureka show OUT_OF_SERVICE? Is Consul check passing? Is the znode deleted? |
| DiscoveryClient instances | Does the consumer still see the old instance? |
| LoadBalancer selection | Does the consumer still pick the old instance? |
| Request count by instance ID | Did the old instance receive new requests after drain converged? |
| In-flight requests | Were any requests cut off on SIGTERM? |
| HTTP 5xx/timeouts | Did the rollout cause errors exceeding SLO? |
| Shutdown logs | Did the app finish graceful shutdown or get SIGKILL? |

To verify "stopped receiving traffic," do not merely count total requests before and after rollout. Record the drain timestamp and instance ID; identify the last new request reaching the old instance. Requests that began before draining may finish after draining and must not be miscounted as new traffic.

## 15. Test Scenarios and PASS/FAIL Criteria

| Scenario | Action | PASS When | FAIL When |
|---|---|---|---|
| Normal rollout | Update image from 2.4.0 to 2.5.0. | New Pod is Ready before old Pod scales down; traffic shifts gradually. | Capacity drops below threshold or request errors exceed SLO. |
| Readiness fail on new Pod | Force readiness endpoint to return errors. | Deployment keeps old Pods and does not count new Pod available. | New Pod receives traffic while unready. |
| Drain old Pod | Call /internal/drain. | Readiness fails, endpoint is no longer ready, and new requests move to other instances. | Old instance keeps receiving new requests after drain window. |
| Long in-flight request | Send a long-running request then start rollout. | Request completes within shutdown budget. | Process terminates before request finishes. |
| Slow registry propagation | Increase fetch interval/cache TTL in test. | Test observes consumer stopping old instance selection while maintaining capacity. | Consumer keeps picking stopped endpoint or unhandled timeouts occur. |
| Faulty new instance | Deploy new version with startup/readiness failure. | Rollout halts, old version keeps serving. | Deployment deletes all old Pods before new version is Ready. |
| Rollback | Run kubectl rollout undo. | Previous version returns to Ready and traffic stabilizes. | Rollback fails to restore endpoints or schema incompatibility causes errors. |

## 16. Observation and Rollback Commands

Monitor rollout progress:

```bash
kubectl rollout status deployment/payment-service -n commerce
kubectl rollout history deployment/payment-service -n commerce
kubectl get deployment payment-service -n commerce -o wide
kubectl get pods -n commerce -l app=payment-service -w
```

Inspect EndpointSlice:

```bash
kubectl get endpointslices -n commerce \
  -l kubernetes.io/service-name=payment-service -o yaml
```

Inspect shutdown logs and events:

```bash
kubectl logs <old-pod-name> -n commerce --since=10m
kubectl describe pod <old-pod-name> -n commerce
kubectl get events -n commerce --sort-by=.lastTimestamp
```

If the new version fails criteria:

```bash
kubectl rollout undo deployment/payment-service -n commerce
kubectl rollout status deployment/payment-service -n commerce
```

You can pause rollout to investigate:

```bash
kubectl rollout pause deployment/payment-service -n commerce
kubectl rollout resume deployment/payment-service -n commerce
```

Rolling back an image does not automatically revert database migrations or incompatible message/schema changes. Release design should use expand/contract migrations and maintain compatibility between old and new versions during rollout.

## 17. Common Mistakes

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Old Pod stopped before new Pod Ready | maxUnavailable too large or misconfigured readiness probe. | Use maxUnavailable: 0 when preserving capacity and fix readiness. |
| New Pod Ready too early | Readiness only checks process liveness, not traffic capability. | Use a readiness group aligned with serving requirements. |
| Old Pod still receives requests after drain | Slow endpoint/registry propagation, consumer cache, or connection reuse. | Measure each layer, increase drain window appropriately, and check LoadBalancer/proxy. |
| In-flight requests interrupted | Grace period shorter than request/shutdown duration. | Increase shutdown budget or bound request duration. |
| preStop fails to call drain endpoint | Image lacks curl, wrong port/path, or endpoint blocked by security. | Check hook events/logs, add suitable tool/script, and restrict internal access. |
| Readiness fails and liveness also fails | Shared health logic without distinguishing readiness/liveness. | Separate health groups; do not restart just because an instance is draining. |
| Eureka consumer still sees old instance | Status/deregister not propagated or registry fetch/LB cache stale. | Mark OUT_OF_SERVICE, wait for fetch/cache, and verify consumer. |
| Consul still returns critical instance | Catalog record persists; query does not filter passing. | Use proper health query, enable query-passing, and verify policy. |
| Kubernetes DNS reaches old Pod | Headless DNS/cache or client connection pool holds IP. | Check TTL/resolver/connection pool; prefer Service ClusterIP if Pod identity isn't needed. |
| Rollout stalls | New Pod not Ready, insufficient surge resources, or startup timeout. | Inspect events, quotas, capacity, and probes. |
| SIGKILL occurs | Hook plus shutdown exceed terminationGracePeriodSeconds. | Recalculate total duration and increase grace period deliberately. |
| Rollback succeeds but requests still error | New schema/config incompatible with old version or registry/cache not converged. | Check backward compatibility and discovery state after rollback. |

## 18. Production Checklist

- Deployment has maxSurge/maxUnavailable aligned with capacity and cluster resources.
- Readiness accurately reflects ability to accept requests; liveness is not used as a drain signal.
- Spring Boot graceful shutdown is enabled with an appropriate timeout.
- Internal drain endpoint is secured and invoked successfully in preStop.
- preStop + propagation + in-flight requests + shutdown fit within termination grace period.
- New Pods receive traffic only after passing readiness and minimum stabilization time.
- Service selector is stable so both old and new Pods are managed together during rollout.
- Eureka/Consul/Kubernetes discovery semantics are verified separately; do not assume readiness automatically updates every registry.
- Consumer cache and LoadBalancer cache convergence times are measured.
- Ingress/load balancer/service mesh has compatible connection draining configuration.
- Logs/metrics include instance ID and version to identify which Pod served each request.
- Long requests, health failures, slow registry propagation, and rollback are tested.
- Database/schema/message contracts remain compatible while both versions coexist.
- Alerts are configured for 5xx errors, timeouts, unavailable replicas, and rollout progress deadlines.

## Conclusion

Safe rolling updates require ensuring new instances are ready before old instances leave traffic, while giving routing and discovery layers enough time to stop selecting old instances. Readiness controls traffic eligibility, preStop creates the drain window, Spring Boot graceful shutdown completes active requests, and registries/LoadBalancer update instance lists via their own mechanisms.

Do not equate a Terminating Pod with all consumers having stopped sending requests. Observe EndpointSlices, registry status, DiscoveryClient, LoadBalancer selection, and request logs by instance ID. By combining maxSurge/maxUnavailable strategies, readiness, draining, connection draining, and rollback, you can deploy new versions while maintaining capacity and keeping disruption within SLOs.

## References

- Kubernetes — Deployments and rolling updates: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- Kubernetes — Pod lifecycle and termination: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Kubernetes — Probes: https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/
- Spring Boot — Graceful shutdown: https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html
- Spring Boot — Application availability: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Cloud Netflix — Eureka: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Spring Cloud Consul — Service discovery: https://docs.spring.io/spring-cloud-consul/reference/discovery.html

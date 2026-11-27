# Health Probes and Container Service Deployment Lifecycle

## Lesson Objectives

After this lesson, you will be able to:

- Distinguish startup, readiness, and liveness health probes for containers.
- Design health check endpoints suited to each probe's role.
- Configure probes for a container service running on Kubernetes.
- Explain how health probes participate in admitting new versions into service, draining old versions from traffic, and recovering from failed deployments.
- Inspect deployment status and recognize common probe misconfigurations.

## 1. Why Do Container Services Need Health Probes?

A container in the `Running` state only indicates that the main process has been started. It does not prove that the application has loaded its configuration, opened connections to dependencies, finished initialization, or can serve requests. Conversely, a process may still be running while deadlocked, starved of resources, or no longer able to handle requests.

Health probes are periodic checks that inform the orchestration platform which phase a container is in and whether it can serve traffic. Probe results can cause the platform to wait during startup, remove an instance from traffic rotation, restart the container, or mark a deployment as failing requirements.

In multi-replica services, probes help the load balancer send requests only to ready instances. During version updates, probes help the system shift traffic to new instances only after the application is genuinely ready, while detecting faulty new versions so deployments can halt or roll back.

## 2. Three Probe Types and Their Responsibilities

The three common probe types in Kubernetes serve distinct purposes. You should not use a single check for all three purposes.

| Probe Type | Question to Answer | On Failure | Example Scenario |
|---|---|---|---|
| Startup probe | Has the application finished initializing? | Container is considered failed to start and may be restarted per `restartPolicy`. | Application takes 50 seconds to load a model or run startup migrations. |
| Readiness probe | Can this instance accept requests right now? | Instance is marked unready and excluded from normal serving endpoints. The container is not restarted solely because readiness fails. | Application is warming a cache or lost connection to a required database. |
| Liveness probe | Is the process still healthy enough at a minimum level to keep running? | Kubelet terminates the container; the Pod's restart policy governs restarting it. | Event loop is hung, deadlocked, or process is no longer responsive. |

**Startup probes** are intended for applications with long or variable startup times. When a startup probe is configured, Kubernetes delays running readiness and liveness probes for that container until the startup probe succeeds. This prevents the liveness probe from concluding the app is hung while it is still legitimately initializing.

**Readiness probes** govern whether an instance should receive traffic. Readiness can flip between success and failure multiple times over a container's lifecycle—such as when the app is overloaded or a required dependency becomes temporarily unavailable. A failed readiness check does not mean the container should be restarted.

**Liveness probes** detect unrecoverable process states. The check should focus on the application's internal liveness, such as whether the internal HTTP server responds or the event loop makes progress. If liveness depends directly on every external service, a database outage can trigger simultaneous restarts across all containers even though the processes themselves are healthy.

## 3. Designing Health Check Endpoints

An HTTP application can expose three dedicated endpoints:

- `/health/startup`: returns success once mandatory initialization steps complete.
- `/health/ready`: returns success when the instance can accept and process real requests.
- `/health/live`: returns success while the process remains responsive and has not entered an unrecoverable state.

For HTTP probes, status codes in the 200–399 range are treated as success by Kubernetes. You can establish a convention where endpoints return `200 OK` when healthy and `503 Service Unavailable` when not. Endpoints should respond quickly, enforce clear timeouts, and avoid executing heavy queries.

When designing them, separate responsibilities as follows:

1. Startup verifies steps required to begin serving: loading configuration, opening listeners, initializing internal components, and completing mandatory boot tasks.
2. Readiness verifies the ability to handle the request types the service commits to serving. Include a dependency in this check only if lacking it truly prevents the instance from serving safely.
3. Liveness checks internal process health. Do not call external provider APIs or run heavy database queries on every liveness check.

For example, an orders service requires a database to write new orders. Readiness can verify that the connection pool can still lease connections and that application state allows writing orders. If the database disconnects, the instance can temporarily stop accepting write requests. Liveness can continue succeeding if the HTTP process operates normally. Once the database recovers, readiness succeeds again and the instance returns to service without a restart.

Not every dependency failure needs to fail readiness. If the application can still serve partial functionality using caches or a designed degraded mode, reflect that state accurately according to the service contract. If readiness checks too many non-essential dependencies, an outage in a secondary system can pull every replica out of the load balancer and cause a wider outage.

## 4. Configuring Probes for a Container Service on Kubernetes

The example below deploys three replicas of an orders API. The application listens on port `8080`; the startup probe allows up to roughly two minutes for initialization; readiness checks traffic-handling capability; liveness detects an unresponsive process.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  minReadySeconds: 10
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: api
          image: registry.example.com/orders-api:1.8.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 24
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 2
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
```

The parameters in this example are a starting point and must be tuned to actual startup times and latency:

- `periodSeconds` is the interval between probes.
- `timeoutSeconds` is the maximum wait time for a single probe response.
- `failureThreshold` is the number of consecutive failures before the probe is marked failed.
- `successThreshold` is the number of consecutive successes needed for readiness to transition back to ready. For liveness and startup, this value must be `1`.
- `minReadySeconds` requires a Pod to remain Ready for a period before the Deployment considers it stably available for the rollout.
- `maxSurge: 1` allows creating at most one extra Pod during updates; `maxUnavailable: 0` requires maintaining the full desired available replica count throughout the rollout. The cluster must have sufficient resources to schedule the extra Pod.

The startup probe in the example uses a 5-second period and a threshold of 24 failures, creating an initialization window of approximately 120 seconds. Set thresholds based on startup duration under realistic load and resource conditions, plus a sensible buffer. If the application frequently exceeds the threshold during startup, investigate the root cause or tune the threshold rather than raising it indefinitely.

Kubernetes also supports TCP, exec, and gRPC probes. TCP only confirms the port accepts connections, not that the app processes requests correctly. Exec runs a command inside the container, so it depends on tools shipped in the image and adds process overhead. HTTP fits when the app has dedicated health endpoints; gRPC fits services implementing the gRPC health checking protocol.

## 5. Health Probes in Managed Container Services

Cloud platforms can involve multiple health checking layers. Identify which layer checks the container, which checks the task or instance, and which governs traffic routing.

**Example with Amazon ECS and Application Load Balancer (ALB):** a task definition can declare a container health check using a command executed inside the container. Simultaneously, the ALB checks targets via target group health checks. The container health check reflects process health inside the container; the ALB health check reflects application reachability from the load balancer's perspective. The two complement each other without replacing one another. The service's health check grace period must be long enough for a new task to boot before the platform evaluates unhealthy status.

**Example with Kubernetes on EKS, GKE, or AKS:** Deployment manages replica counts and rollouts; kubelet executes startup, readiness, and liveness probes; Service and EndpointSlice reflect Pods eligible to receive traffic. A load balancer or ingress may perform additional health checks at the network layer into the application. When multiple layers probe simultaneously, paths, ports, timeouts, and expected responses must align.

An outer-layer probe can fail even when an in-container probe succeeds—for instance, when the application listens on `127.0.0.1` instead of an address reachable from the Pod network, or when a security rule blocks traffic to the target. When investigating, check each hop from container, Pod, and Service out to the load balancer.

## 6. Container Service Deployment Lifecycle

A safe deployment typically progresses through the following stages:

1. **Build and package:** build the image from source, run required checks, and apply an immutable version tag. For critical environments, record the image digest to pinpoint the exact deployed artifact.
2. **Push image and create revision:** push the image to the registry and update the service or Deployment config so the platform creates a new revision or ReplicaSet.
3. **Schedule and boot:** the platform allocates resources, pulls the image, creates the container, and starts the process. The startup probe gives the app time to finish initialization.
4. **Readiness checking:** once startup succeeds, the readiness probe begins determining whether the instance can accept traffic. Unready instances are excluded from normal serving endpoints.
5. **Traffic shifting:** as new replicas become ready, the rollout mechanism gradually shifts traffic or replaces old replicas. Monitor errors, latency, and success rates during this stage.
6. **Drain and graceful shutdown:** old instances stop accepting new requests, finish in-flight requests within the allowed window, and then terminate. The application must handle `SIGTERM`, close connections, and release resources before the grace period expires.
7. **Complete or roll back:** if the new revision stabilizes, complete the rollout. If probes fail persistently, Pods crash-loop, or service metrics degrade, halt the rollout and restore the previous revision.

Readiness plays a key role in draining an instance from traffic. When shutdown starts, the app can fail readiness first, wait briefly for endpoint updates and load balancer propagation, finish in-flight requests, and exit upon `SIGTERM`. You can use lifecycle hooks such as `preStop` to trigger drain mode, keeping in mind that hook execution and shutdown both share the `terminationGracePeriodSeconds` budget. Ensure the app has realistic time to complete requests; if the grace period is too short, in-flight requests may be severed.

With rolling updates, `maxUnavailable: 0` maintains full available capacity while swapping versions, though it requires extra resources for surge Pods and can stall rollouts if readiness probes are misconfigured. Traffic-splitting or revision-based shifting policies on managed platforms can shrink blast radius, provided clear stop and rollback criteria are defined.

## 7. Trade-Offs and Common Misconfigurations

| Decision | Benefit | Risk to Control |
|---|---|---|
| Readiness checks many dependencies | Prevents accepting requests when the service cannot complete business logic. | A dependency outage can pull every replica out of rotation simultaneously. |
| Liveness checks databases or external APIs | Appears to cover more components. | Network blips or external outages trigger mass restarts and worsen incidents. |
| Timeout too short | Detects unresponsive instances quickly. | High load or brief GC pauses cause false probe failures. |
| Failure threshold too low | Detects failures rapidly. | A brief latency spike triggers restarts or drops instances from traffic. |
| Startup window too short | Shortens time to detect boot failures. | Slow but valid app startups get stuck in restart loops. |
| Startup window too long | Tolerates variable app startup times. | Real boot failures are detected late, dragging out rollouts. |
| Readiness checks TCP port only | Simple config with minimal dependencies. | Port is open before the app can actually process business requests. |

Warning signs to watch for:

- `CrashLoopBackOff`: inspect logs from the previous terminated container, Pod events, and startup/liveness results; check config, resources, and startup duration.
- Pod `Running` but `NotReady`: inspect readiness endpoints, dependencies, ports, paths, and HTTP status codes.
- Stalled rollout: check whether new Pods reach Ready, `minReadySeconds`, resource availability, image pulls, and surge limits.
- All replicas lose Ready together: check shared dependencies, network policies, DNS, certificates, secrets, or overly strict readiness logic.
- Instances restart under load spikes: check timeouts, CPU throttling, memory limits, GC pauses, and whether health endpoints contend for resources with real requests.

## 8. Post-Configuration and Post-Deployment Verification Workflow

Test in a staging environment before applying to a service carrying live traffic.

1. Call all three endpoints directly from inside the Pod or container. Confirm startup succeeds only after initialization completes; readiness reflects traffic-serving capability; and liveness stays healthy when a non-fatal external dependency temporarily fails while the process remains alive.
2. Apply the manifest and watch the rollout:

   ```bash
   kubectl apply -f orders-api.yaml
   kubectl rollout status deployment/orders-api
   kubectl get pods -l app=orders-api -w
   ```

3. If a Pod is not Ready, inspect its status, events, and logs:

   ```bash
   kubectl describe pod <pod-name>
   kubectl logs <pod-name> -c api
   kubectl get endpointslices -l kubernetes.io/service-name=orders-api
   ```

   Inspect `Events` to see which probe failed, failure counts, and messages such as timeouts, connection refused, or invalid HTTP status codes. EndpointSlice confirms which Pods the Service currently includes in its endpoint list.

4. Deliberately test fault scenarios in staging: prolong startup time, make the readiness endpoint fail, temporarily cut a required dependency, and simulate an unresponsive process. Observe expected behavior: startup waits within bounds, readiness removes the instance from traffic without restarting, and liveness triggers a restart when the process is truly unhealthy.
5. Verify graceful shutdown: send a termination signal or delete a Pod, confirm the instance stops receiving new requests, in-flight requests finish within the grace period, and remaining Pods continue serving.
6. After rollout, check error rates, latency, restart counts, time to Ready, and revision status. If you need to restore a Deployment to the previous revision:

   ```bash
   kubectl rollout history deployment/orders-api
   kubectl rollout undo deployment/orders-api
   ```

For services on other platforms, inspect the corresponding task/revision status page, deployment events, container logs, and target health status. Verify both internal container health checks and load balancer health checks if the platform uses both.

## 9. Operations Checklist

- [ ] Startup, readiness, and liveness probes have distinct purposes aligned with the app lifecycle.
- [ ] Health endpoints respond quickly, require no user authentication, and run no heavy queries.
- [ ] Liveness does not depend on external services that could cause cascading restarts.
- [ ] Readiness checks only conditions genuinely needed to accept requests.
- [ ] Timeouts, periods, and failure thresholds are grounded in real startup and load measurements.
- [ ] Rollouts have sufficient resources, minimum replica counts, and proper startup wait windows.
- [ ] Application handles `SIGTERM`, drains requests, and exits within the grace period.
- [ ] Tested slow startup, readiness failure, liveness failure, and rollback in a test environment.
- [ ] Post-deployment monitoring tracks probe failures, restarts, rollout duration, error rates, and latency.

## Conclusion

Health probes inform the platform when a container has booted, when an instance can take traffic, and when a process needs to be restarted. Combining well-designed probes with rolling updates, graceful shutdown, metric tracking, and rollbacks enables container services to ship new versions more reliably, reduce disruptions, and shorten incident recovery times.

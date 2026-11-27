# Logs, Metrics, and Troubleshooting Container Restarts

Containers can restart when the main process exits, is terminated by the runtime, exceeds memory limits, fails health checks, or when the underlying node fails. A single restart may simply be normal behavior during a rollout; repeated consecutive restarts can disrupt requests, wipe ephemeral data, and trap the workload in an unrecoverable crash loop.

To troubleshoot properly, preserve evidence from the prior execution, identify the container's termination reason, correlate logs with platform metrics and events, and only then decide whether to fix configuration, roll back, increase resources, or adjust the restart policy. A restart policy tells the runtime to retry starting the container; it does not fix application bugs or guarantee data preservation.

## 1. Distinguishing Container, Container Process, and Pod

A container is an execution environment instantiated from an image. In most models, a container runs a primary process; when that process exits, the container transitions to a stopped state. The runtime or orchestrator can recreate the process or container according to the restart policy.

In Kubernetes, a Pod is the smallest deployment unit and may contain one or more containers. When a container inside a Pod exits, kubelet can restart that container within the same Pod. When a Pod is deleted and recreated, the new Pod receives a new UID; its name may be reused, such as with a StatefulSet. The new Pod's restart count starts back at zero. Therefore, distinguish between:

- **Container restart:** a container inside the same Pod is restarted; the Pod UID typically remains unchanged and `restartCount` increments.
- **Pod replacement:** the old Pod is deleted and the Deployment/StatefulSet/Job creates a new Pod; the Pod UID changes.
- **Node replacement:** the machine hosting the Pod is replaced or lost; the scheduler places the workload on another node if the controller and storage permit.
- **Application restart:** a child process or worker inside the container restarts itself while the main container process stays alive; the runtime may not increment `restartCount`.

Logs, metrics, and events must capture enough identifiers to distinguish these cases. Looking only at Pod name or container name is insufficient because names can be reused; also record namespace, Pod UID, container ID, node, and timestamp.

## 2. Common Causes of Container Restarts

A container can terminate for several reasons:

| Cause | Typical Signs | Where to Check |
|---|---|---|
| Application exits on its own | Non-zero exit code, exception, or fatal log | Application logs, config, dependencies, and exit codes |
| Normal task completion | Exit code 0 | Workload type, command/args, and restart policy |
| OOM kill | `OOMKilled`, memory events, process killed with SIGKILL | Memory limit, cgroups, node pressure, and runtime metrics |
| Liveness probe failure | Probe failed events, container restart | Endpoint, timeout, startup duration, and probe thresholds |
| Terminated during rollout/scale | SIGTERM, common exit code 143 | Deployment events, termination grace period, and shutdown logic |
| Node or runtime failure | Pod evicted, node `NotReady`, runtime events | Kubelet, container runtime, node conditions, and cloud events |
| Misconfiguration | Missing env vars, secrets, files, or permissions | Manifest, ConfigMap/Secret, volume mounts, and UID/GID |
| Image/command cannot start | `ImagePullBackOff`, `ErrImagePull`, `CreateContainerError`, or process fails to launch | Image reference, registry, entrypoint, permissions, and architecture |

A container restart is not automatically an incident. For example, a Job finishing and exiting is expected behavior. Conversely, a container remaining in the `Running` state does not prove the app is healthy; the process may be hung or failing to serve requests.

## 3. Exit Codes and Termination Reasons

An exit code is the initial clue to guide investigation, not complete proof of the root cause.

- `0`: the process exited cleanly per application convention. For long-running services, exit code 0 can still trigger a restart if policy requires continuous execution.
- Non-zero values: the application or runtime reported an abnormal exit; check logs and program documentation for exact meanings.
- `137`: typically corresponds to `128 + 9`, meaning the process received SIGKILL. OOM kill is a common culprit, though administrators or the runtime can also send SIGKILL.
- `143`: typically corresponds to `128 + 15`, meaning the process received SIGTERM. Can occur during rollouts or controlled shutdowns; the app may not have finished shutting down.

Never conclude OOM from exit code 137 alone. Correlate the termination reason, kernel/cgroup events, memory usage, and termination timestamp. Similarly, exit code 143 does not by itself prove shutdown completed cleanly; inspect application logs and graceful termination timing.

In Kubernetes, container status typically provides `state`, `lastState`, `reason`, `exitCode`, `startedAt`, and `finishedAt`. The `lastState.terminated` field is particularly useful because it describes the most recent termination of the current container.

## 4. Restart Policies in Docker

Docker supports these common restart policies:

| Policy | General Behavior |
|---|---|
| `no` | Do not automatically restart when the container exits; this is the default if no policy is specified |
| `on-failure` | Restart when the process exits with a non-zero exit code; retry count can be capped |
| `always` | Docker attempts to restart the container whenever it stops; the container may also start when the Docker daemon restarts per policy conditions |
| `unless-stopped` | Similar to `always`, except it preserves manual stop state across daemon restarts per Docker semantics |

Example:

```bash
docker run -d \
  --name orders-api \
  --restart unless-stopped \
  -p 8080:8080 \
  registry.example.com/commerce/orders-api:1.4.0
```

Capping retry attempts with `on-failure`:

```bash
docker run -d \
  --name batch-worker \
  --restart on-failure:5 \
  registry.example.com/commerce/batch-worker:1.4.0
```

A restart policy applies only to the Docker-managed container lifecycle. It does not replace health checks, monitoring, data durability, or application-level retry logic. If a container exits repeatedly due to a bad config, `always` can trigger a restart loop and rapidly fill logs.

You can inspect policy and state:

```bash
docker inspect orders-api --format '{{json .HostConfig.RestartPolicy}}'
docker inspect orders-api --format '{{json .State}}'
```

## 5. Restart Policies in Kubernetes

Kubernetes sets `restartPolicy` at the Pod level. Valid values are `Always`, `OnFailure`, and `Never`.

| Policy | General Behavior | Typical Workloads |
|---|---|---|
| `Always` | Kubelet restarts the container whenever it terminates, regardless of exit code | Deployments, StatefulSets, and long-running service workloads |
| `OnFailure` | Restarts the container only when it exits with a non-zero exit code | Jobs needing in-Pod container retries |
| `Never` | Never restarts a terminated container inside that Pod | Jobs where the controller creates a new Pod or handles errors via its own policy |

Deployments and StatefulSets normally use `restartPolicy: Always`; Job Pod templates typically use `OnFailure` or `Never`. Controllers like Job or Deployment manage Pods according to workload semantics. You cannot set `restartPolicy: OnFailure` on a Deployment Pod template.

Example service Pod:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-api
spec:
  restartPolicy: Always
  containers:
    - name: api
      image: registry.example.com/commerce/orders-api:1.4.0
      ports:
        - name: http
          containerPort: 8080
```

`CrashLoopBackOff` is Kubernetes's backoff state when a container repeatedly terminates and kubelet delays the next restart attempt. It is neither a separate restart policy nor a root cause. You must look up the termination reason and logs from the previous execution.

## 6. Retrieving Logs from Current and Previous Containers

When a container restarts, logs from the prior execution may no longer appear in the active log stream. Collect logs before the Pod is replaced or the node rotates log files.

With Docker:

```bash
docker logs --timestamps --since 30m orders-api
docker logs --timestamps --tail 200 orders-api
```

With Kubernetes:

```bash
kubectl logs pod/orders-api -n production -c api
kubectl logs pod/orders-api -n production -c api --previous
```

`--previous` requests logs from the previous container instance if still retained and accessible by the runtime. It is not a long-term log archive; if the Pod has been replaced or the node already pruned logs, the data may be gone. For multi-container Pods, specify `-c` to avoid querying the wrong container.

To fetch logs by label:

```bash
kubectl logs -n production -l app=orders-api \
  --all-containers=true --prefix --since=20m
```

`--prefix` helps distinguish log sources. When investigating restarts, save logs, Pod descriptions, and events before deleting a Pod or rolling out again, since those actions can destroy needed evidence.

## 7. Collecting Status and Events in Kubernetes

Essential commands:

```bash
kubectl get pods -n production -o wide
kubectl describe pod orders-api -n production
kubectl get events -n production --sort-by=.lastTimestamp
kubectl get pod orders-api -n production -o yaml
```

Focus on these fields:

- `status.containerStatuses[].restartCount`: number of container restarts in the current Pod.
- `state.waiting.reason`: reason the container is not running, such as `CrashLoopBackOff` or `ImagePullBackOff`.
- `lastState.terminated.reason`: reason for the previous termination, such as `OOMKilled` or `Error`.
- `lastState.terminated.exitCode`: exit code of the previous termination.
- `startedAt` and `finishedAt`: start and finish timestamps.
- `ready`: whether the container is currently marked ready.
- Events: probe failures, image pull errors, evictions, scheduling, or mount errors.

Example checking restart count and termination reason using JSONPath:

```bash
kubectl get pod orders-api -n production \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" restarts="}{.restartCount}{" reason="}{.lastState.terminated.reason}{" exit="}{.lastState.terminated.exitCode}{"\n"}{end}'
```

If the Pod is managed by a Deployment, inspect the ReplicaSet and rollout as well:

```bash
kubectl get deployment,replicaset -n production
kubectl rollout status deployment/orders-api -n production
kubectl rollout history deployment/orders-api -n production
```

Replace the resource names in the examples for your environment. `kubectl describe` is usually a great starting point because it combines status, probe configurations, and related events.

## 8. Docker Diagnostics: State, Events, and Resources

Docker exposes container state and events to pinpoint when a container starts, dies, restarts, or gets killed:

```bash
docker inspect orders-api --format '{{json .State}}'
docker inspect orders-api --format '{{.RestartCount}}'
docker events --since 30m --filter container=orders-api
docker stats --no-stream orders-api
```

Information to record:

- `Status`, `Running`, `Restarting`, `OOMKilled`, and `ExitCode` inside state.
- `StartedAt` and `FinishedAt` to align timelines.
- `RestartCount` to see how many times the container has restarted in its current lifecycle.
- `OOMKilled` and memory limits to check for memory kills.
- `die`, `start`, `restart`, `kill`, or `oom` events emitted by the runtime.
- CPU, memory, network, and block I/O before and after the incident.

`docker stats` is a point-in-time snapshot, not a substitute for time-series metrics. When failures happen rapidly, you need a monitoring system recording metrics continuously so you can review history.

## 9. Designing Logs to Investigate Restarts

Containerized applications should write operational logs to `stdout` and `stderr` for collection by the runtime or platform. Writing logs solely to files in the writable layer risks losing logs when containers are removed or replaced. If file logging is required, use a volume or file-collection agent with clear lifecycle policies.

Structured logs should include useful fields:

| Field | Purpose |
|---|---|
| `timestamp` | Order events chronologically; prefer UTC or a consistent time format |
| `severity` | Distinguish DEBUG, INFO, WARN, ERROR, FATAL |
| `service.name` | Identify the workload |
| `environment` | Distinguish production, staging, and development |
| `container.id` | Identify the container instance |
| `pod.name`, `pod.uid`, `namespace` | Locate the workload in Kubernetes |
| `node.name` or `host.id` | Identify the host running the container |
| `restart.sequence` or startup ID | Distinguish separate runs if generated by the application |
| `trace_id`, `span_id`, `request_id` | Correlate logs with requests and traces when context exists |
| `event` / `error.type` | Categorize the event and error class |
| `message` | Concise, contextual explanation |

Example JSON log entry:

```json
{
  "timestamp": "2026-11-22T08:15:31.442Z",
  "severity": "ERROR",
  "service.name": "orders-api",
  "environment": "production",
  "namespace": "production",
  "pod.name": "orders-api-7b9c8f6d4d-k2m8p",
  "container.name": "api",
  "container.id": "containerd://a12b34c56d",
  "event": "database_connection_failed",
  "error.type": "ConnectionTimeout",
  "message": "Could not obtain a database connection before timeout"
}
```

This is an illustrative schema; align field names with your logging pipeline. Never log passwords, access tokens, cookies, private keys, sensitive request bodies, or unnecessary personal data. Error logs should include stack traces when helpful, but bound payload sizes and avoid emitting identical stack traces thousands of times during a restart loop.

## 10. Deliberate Startup and Shutdown Logging

A container is hard to troubleshoot if its logs do not clearly show lifecycle transitions. Applications should log these events:

- Process start and build/image version.
- Configuration loading and validation of required dependencies.
- Opening listening ports or starting consumers.
- Readiness transitioning to serving state.
- Receiving a shutdown signal and starting drain.
- Stopping acceptance of new requests/messages.
- Completion or timeout when closing connections, flushing data, and stopping workers.
- Reason for an intentional application exit whenever determinable.

Do not dump secrets or full configs containing credentials at startup. Log only config names, statuses, and non-sensitive values needed for troubleshooting.

For multi-worker applications, startup logs should report worker counts, concurrency, and queue state. During shutdown, log in-flight request counts and drain results to distinguish crash restarts from rollout restarts.

## 11. Metrics to Monitor During Container Restarts

Logs reveal event details; metrics reveal trends and blast radius. Key metrics include:

| Metric | Meaning | How to Use |
|---|---|---|
| Container restart count/rate | Number or frequency of restarts | Detect crash loops and compare by service/node |
| Last termination reason/exit code | Most recent termination cause and code | Group failures into OOM, app exit, or killed |
| Container memory working set | Active memory in use | Compare against memory limits and OOM events |
| Memory limit utilization | Usage relative to limit | Spot processes approaching their ceiling |
| CPU usage/throttling | CPU consumed and throttled duration | Diagnose slow startups, timeouts, or undersized CPU limits |
| Probe failure count | Count of failed liveness/readiness/startup probes | Identify broken endpoints or misconfigured probes |
| Request rate/error/latency | User impact | Determine whether restarts cause 5xx errors or latency spikes |
| Queue depth/consumer lag | Pending work volume | Spot worker restarts causing backlogs to climb |
| Node condition/pressure | Host machine health | Separate container bugs from node memory/disk/PID pressure |
| Image pull/startup duration | Container replacement latency | Evaluate recovery speed and rollout duration |

Observe restart counts alongside timestamps, termination reasons, memory, CPU, probe events, and service SLIs. An isolated restart may not be alarming; repeated restarts across multiple replicas or accompanied by rising error rates demand immediate priority.

## 12. Docker Log Limits and Collection

Docker uses a logging driver to forward stdout/stderr to a log destination. The default driver depends on daemon configuration. Check it with:

```bash
docker info --format '{{.LoggingDriver}}'
docker inspect orders-api --format '{{.HostConfig.LogConfig.Type}}'
```

With `json-file`, you can configure rotation when creating a container:

```bash
docker run -d \
  --name orders-api \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=5 \
  registry.example.com/commerce/orders-api:1.4.0
```

The limits above are examples. Size `max-size` and `max-file` to match log generation rate and required local retention on the node. Rotation prevents logs from filling the disk, but older logs are evicted from the node; ship logs to a centralized system when long-term investigation is required.

If using a logging driver that ships directly to a backend, verify buffering, retries, network outage handling, and behavior when the backend rejects logs. A poorly configured logging setup can block the application or drop logs when the collector goes down.

## 13. Log Collection on Kubernetes

Kubernetes normally captures container stdout/stderr via the container runtime and kubelet. Log files on nodes may rotate according to kubelet/runtime settings; retrieval via `kubectl logs` depends on those files still existing.

Common centralized logging options include:

- DaemonSet agents running on every node to tail container logs.
- Managed logging agents or platform observability services.
- Sidecar collectors for special cases needing custom log parsing, though sidecars add resource and operational overhead.
- Applications shipping logs directly over a supported protocol, provided proper buffering and backpressure protections exist.

With node-level agents, filter by namespace, container, labels, and log level; avoid duplicate collection between agents and sidecars. With sidecars, budget memory/CPU, shared volumes, and behavior if the sidecar crashes.

Set retention aligned with ingestion volume and investigative needs. Startup, shutdown, error, and audit logs may need different retention policies than routine debug logs.

## 14. Kubelet and Container Runtime Logs

If multiple containers on the same node restart together or Pods cannot create containers, the fault may lie in the node or runtime rather than the application. When node access is available, inspect kubelet and container runtime status and logs per the OS and distribution.

Example on Linux using systemd:

```bash
sudo journalctl -u kubelet --since "30 minutes ago" --no-pager
sudo journalctl -u containerd --since "30 minutes ago" --no-pager
```

Service names and log access methods vary across managed Kubernetes offerings, runtimes, or distributions. Some platforms forbid direct node access; in those cases, rely on node problem detectors, control plane events, or provider-managed log services.

When disk pressure, inode exhaustion, PID exhaustion, or container runtime disconnects occur, multiple Pods may suffer simultaneously. Do not merely restart individual containers while the underlying node remains unhealthy.

## 15. Health Checks: Liveness, Readiness, and Startup Probes

Probes determine whether an application has booted, stays alive, and is ready to receive traffic. Misusing probes is a frequent cause of unnecessary container restarts.

| Probe | Question | On Failure |
|---|---|---|
| Startup probe | Has the application finished booting? | Kubelet keeps retrying up to threshold; once exceeded, container is restarted |
| Liveness probe | Is the process still capable of operating? | Kubelet restarts the container after configured consecutive failures |
| Readiness probe | Can the application accept traffic right now? | Container is marked not ready and removed from matching service endpoints |

Startup probes help slow-starting apps. While a startup probe is present, liveness and readiness probes stay inactive until the startup probe succeeds. This prevents liveness probes from killing the app during legitimate warm-up.

Readiness failure does not restart a container. It simply signals that the container is not ready for traffic. Liveness failure can trigger a restart. Separating these behaviors prevents using liveness to handle every transient dependency issue.

### Probe Configuration Example

```yaml
containers:
  - name: api
    image: registry.example.com/commerce/orders-api:1.4.0
    ports:
      - name: http
        containerPort: 8080
    startupProbe:
      httpGet:
        path: /health/startup
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 30
    livenessProbe:
      httpGet:
        path: /health/live
        port: http
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /health/ready
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2
```

This is an illustrative example; endpoints and thresholds must fit startup duration, latency, and application behavior. `failureThreshold` must tolerate brief jitter while still catching genuine failures within SLO bounds.

Liveness endpoints should verify meaningful internal state, such as event loop responsiveness. Never fail liveness merely because a database or external API temporarily disconnects; if every replica restarts together during a dependency outage, the system can trigger a restart storm and slow recovery. Readiness may reflect mandatory dependencies when the app genuinely cannot serve requests while that dependency is down.

## 16. Graceful Shutdown and Termination Grace Period

When a container stops due to a rollout, scale-in, or Pod deletion, the runtime typically sends SIGTERM to the main process and waits for the grace period. If the process has not exited when time expires, the runtime can send SIGKILL.

Applications should:

1. Catch SIGTERM or the corresponding shutdown signal.
2. Stop accepting new requests/messages.
3. Mark readiness false to stop receiving new traffic.
4. Complete or cleanly abort in-flight requests.
5. Commit/flush durable state and close connection pools.
6. Stop workers and exit before the deadline.

In Kubernetes, `terminationGracePeriodSeconds` defines the Pod termination timeout. Any `preStop` hook executes inside that grace period and consumes part of the shutdown budget. Setting the grace period too short risks SIGKILLing the app; setting it too long slows rollouts and scale-in.

Applications should explicitly log when SIGTERM arrives, when draining starts, and when shutdown finishes. If containers frequently exit with code 137 during rollouts, inspect the grace period, request processing time, and signal handling before assuming OOM.

## 17. Investigating OOMs and Memory Limits

A container can be OOM-killed when exceeding its cgroup memory limit, even if the node still has free RAM. Inspect container memory usage, configured limits, and kernel/runtime status together.

In Kubernetes:

```bash
kubectl describe pod orders-api -n production
kubectl get pod orders-api -n production \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" reason="}{.lastState.terminated.reason}{" exit="}{.lastState.terminated.exitCode}{"\n"}{end}'
kubectl top pod orders-api -n production --containers
```

`kubectl top` requires Metrics Server or a compatible metrics source; it shows current usage rather than historical values at the moment of OOM. Use Prometheus, managed monitoring, or a metrics backend to view pre-incident trends.

Check:

- Memory working set and memory limit prior to the restart.
- Heap, native memory, thread stacks, caches, and runtime buffers.
- `requests.memory` and `limits.memory` in the Pod spec.
- `OOMKilled` events, node memory pressure, and evictions.
- Recent load changes, releases, batch jobs, or cache warm-ups near the failure timestamp.

Do not blindly raise limits if memory grows continuously from a leak. Determine the legitimate working set, fix leaks or bound caches/concurrency, and then re-size with headroom.

## 18. Distinguishing Container Restarts from Pod Evictions

A container restart occurs when a container inside a Pod is restarted. Pod eviction occurs when kubelet or the control plane removes a Pod from a node, typically due to node pressure or disruption policies. Pod replacement may schedule a new Pod onto a different node.

Differentiating signals:

- `restartCount` increases while Pod UID stays the same: likely a container restart.
- Pod has reason `Evicted`: inspect the message and node conditions for memory, disk, or PID pressure.
- Old Pod is in `Failed` state and a new Pod is created: a controller may be replacing the Pod.
- Node `NotReady` or `MemoryPressure`/`DiskPressure`: check node-level events and peer workloads on the same node.
- Deployment rollout creates a new ReplicaSet/Pod: check rollout history and image digests.

If multiple Pods on the same node fail simultaneously, prioritize investigating the node, runtime, disk, and network. If only one container's restart count rises, focus on that workload's application, probes, limits, and dependencies.

## 19. Preserving Data and Evidence Across Restarts

A container's writable layer usually shares the container instance's lifecycle. When a container is deleted or a Pod is replaced, data in that layer can be lost. Never store business state, queue checkpoints, or unique logs in the writable layer.

Data classification:

| Data | Appropriate Storage |
|---|---|
| Application logs | stdout/stderr and centralized logging; file logs require explicit volumes/agents |
| Recomputable cache | Memory or ephemeral storage with warm-up policies |
| Business data | Databases, object storage, or persistent volumes per application semantics |
| Batch checkpoints | Durable stores or volumes with matching lifecycles |
| Temporary files | Writable layer, `emptyDir`, or tmpfs if loss on restart is acceptable |
| Crash dumps/core dumps | Dedicated volume with size limits, access controls, and retention |
| Configs/secrets | ConfigMap/Secret or secret manager; never bake back into images |

In Kubernetes, `emptyDir` persists for the Pod's lifetime and survives container restarts within the same Pod, but is deleted when the Pod leaves the node. PersistentVolumes have more independent lifecycles depending on reclaim policies and storage providers; still maintain backups and test attach/failover semantics.

When investigating crashes, save previous logs, termination state, Pod YAML, events, image digests, and metric timelines. If core dumps are needed, pre-configure storage capacity, permissions, and destination paths; do not wait for a container to crash and hope dump data survives.

## 20. Systematic CrashLoopBackOff Troubleshooting

When a Pod enters `CrashLoopBackOff`, investigate in order:

1. Identify the exact Pod, namespace, container, and node.
2. Fetch `kubectl logs --previous` for the terminated container.
3. Run `kubectl describe pod` to read termination reasons and events.
4. Inspect `lastState.terminated`, exit code, started/finished timestamps, and restart count.
5. Check command/args, environment, ConfigMaps, Secrets, volume mounts, and permissions.
6. Correlate memory/CPU limits, OOM events, probe failures, and node pressure.
7. Check dependencies, DNS, certificates, network policies, and service endpoints.
8. Compare the image digest/config against the prior version and most recent rollout.
9. Fix the root cause in the manifest or application; deploy in a controlled manner.
10. Monitor restart counts, readiness, error rates, and logs after applying the fix.

Do not immediately delete a Pod upon seeing `CrashLoopBackOff` before capturing evidence. If you must halt a restart storm to protect dependencies, use controller-appropriate measures per your runbook; altering replicas or re-rolling can destroy old Pods and local logs.

## 21. Example: Container Restart from Misconfiguration

An API is deployed on Kubernetes. After a rollout, new Pods continuously restart. `kubectl get pods` shows `CrashLoopBackOff` and climbing restart counts.

Procedure:

```bash
kubectl logs pod/orders-api-xxxxx -n production -c api --previous
kubectl describe pod orders-api-xxxxx -n production
kubectl get pod orders-api-xxxxx -n production -o yaml
```

The previous logs reveal the application cannot find the `DB_HOST` variable. `describe` shows the container exited with a non-zero exit code, no `OOMKilled`, and no liveness probe failure events. Inspecting the Pod spec reveals the new ConfigMap renamed the key while the Deployment still references the old key name.

Remediation:

1. Verify the exact key names in the ConfigMap and Deployment.
2. Update the manifest through the approved pipeline.
3. Check the diff and rollout status.
4. Confirm new Pods receive the required environment variable without printing secrets to logs.
5. Verify readiness, successful requests, and that restart count stops increasing.

In this case, raising the memory limit or changing the restart policy would not resolve the error. Evidence from previous logs and Pod events quickly isolated the configuration mismatch.

## 22. Example: OOM Restart After Load Increase

A message-processing worker scales consumers from 4 to 20. After deployment, containers hit `OOMKilled` during peak hours. Metrics show the memory working set climbing steadily up to the limit, while queue lag initially drops and then rebounds as workers restart.

Investigation:

- Correlate restart timestamps with memory working set and limits.
- Inspect heap/native memory, in-flight message count, and batch sizes.
- Read pre-restart logs to see which message types the worker was processing.
- Check consumer concurrency and prefetch/buffer settings.
- Identify oversized messages or unbounded caches.

Remediation may involve lowering concurrency, capping batch/prefetch sizes, streaming payloads instead of buffering entire objects in RAM, bounding caches, or increasing memory limits if nodes have capacity. After changes, run a soak test at peak load and watch memory, queue lag, processing rate, errors, and restart counts.

## 23. Alerting and Dashboards for Restarts

Dashboards should slice by service, namespace, workload, Pod, container, and node:

- Restart count and restart rate over time windows.
- Most recent termination reason and exit code.
- Pod readiness, desired/available replicas, and rollout status.
- `OOMKilled` counts, memory working set/limit, and node memory pressure.
- Liveness/readiness/startup probe failures.
- CPU usage/throttling, disk pressure, and PID pressure.
- Request rate, 5xx errors, p95/p99 latency, and queue lag.
- Image version/digest and rollout timestamps.
- Startup, shutdown, exception, and previous container logs.

Base alerts on impact severity:

- A single isolated container restart while peer replicas stay healthy may only warrant logging.
- Repeated restarts within a time window warrant a workload-level alert.
- All replicas restarting or readiness dropping demands a high-severity alert.
- Repeated `OOMKilled`, sustained `CrashLoopBackOff`, or unreached desired replicas require immediate investigation.
- Simultaneous restarts across one node warrant a node/runtime alert.

Never alert solely on cumulative restart count since Pod creation; a long-lived Pod may have one historical restart yet be completely healthy today. Use rate/increase over a sliding window combined with readiness and error rate.

## 24. Runbook for Abnormal Container Restarts

Runbooks should standardize evidence collection and severity-based actions:

**Step 1 — Preserve Evidence**

- Record namespace, Pod UID, container ID, node, image digest, and timestamp.
- Collect previous logs, current logs, `describe` output, Pod YAML, and events.
- Save metric timelines for memory, CPU, probes, requests, and queues.
- Do not delete Pods or manually restart before capturing evidence, unless emergency mitigation requires it.

**Step 2 — Categorize**

- Application exit/exception.
- OOM or resource limit.
- Probe failure.
- Node/runtime/eviction.
- Config/image/secret/volume/network.
- Intentional restart from rollout or scaling.

**Step 3 — Safe Recovery**

- Roll back image/config if a new release caused the fault and data rollback is safe.
- Tune probes if configuration conflicts with startup/health semantics.
- Adjust memory/CPU limits, concurrency, or fix leaks based on metrics.
- Cordon/drain the node if evidence shows node/runtime faults.
- Protect databases/queues against retry storms and duplicate processing.

**Step 4 — Verify**

- Containers stop restarting unexpectedly.
- Pods reach Ready and available replicas meet target.
- Request/error/latency metrics and queue lag return to baseline.
- No data or checkpoints were lost or duplicated.
- Logs, metrics, and alerts record both root cause and resolution.

## 25. Common Mistakes

- **Reading only current logs:** misses errors from the previous container instance. Use `kubectl logs --previous` or centralized log storage.
- **Treating CrashLoopBackOff as the root cause:** it is a backoff state. Inspect termination reasons, exit codes, and previous logs.
- **Assuming exit code 137 always means OOM:** SIGKILL can come from other sources. Verify OOM events and memory metrics.
- **Using liveness to check every dependency:** transient dependency errors restart all containers. Separate liveness from readiness.
- **Overly strict probes:** apps get restarted during warm-up or CPU throttling. Use startup probes and appropriate timeouts.
- **Using `Always` restart policy for every Job type:** tasks exiting cleanly with code 0 can rerun unexpectedly. Pick the right policy and controller.
- **Storing logs only inside the container filesystem:** logs vanish when containers/Pods are replaced. Ship stdout/stderr to centralized storage.
- **Omitting log rotation:** logs fill node disks and disrupt peer workloads. Set retention/rotation matching ingest rates.
- **Raising memory limits without checking for leaks:** only postpones the next OOM. Profile and bound caches/concurrency.
- **Manually restarting before collecting evidence:** destroys state and logs needed for root cause analysis. Capture evidence before intervening whenever feasible.
- **Skipping graceful shutdown:** active requests are severed during rollouts. Handle SIGTERM, drain connections, and configure proper grace periods.

## 26. Operations Checklist

- [ ] Application logs write to stdout/stderr or a file pipeline with clear persistence.
- [ ] Logs include timestamp, service, namespace, Pod UID, container ID, and severity.
- [ ] Logs record startup, shutdown, exceptions, and intentional exit reasons.
- [ ] Centralized logging and retention suffice for investigation after Pod/node replacement.
- [ ] Log rotation caps node disk usage without discarding required logs prematurely.
- [ ] Monitoring tracks restart count/rate, termination reason, exit code, and image digest.
- [ ] Monitoring tracks memory/CPU, limits, OOM events, probe failures, and node pressure.
- [ ] Startup, liveness, and readiness probes have clearly separated semantics.
- [ ] Application handles SIGTERM, drains requests, and shuts down within the grace period.
- [ ] Business data and checkpoints reside on storage with appropriate lifecycles.
- [ ] Runbook captures previous logs, Pod events, YAML, and metric timelines before deleting/recreating.
- [ ] Alerts distinguish single restarts, `CrashLoopBackOff`, repeated OOMs, and node-wide failures.
- [ ] Post-remediation verification confirms readiness, SLIs, queues, and restart rates returned to normal.

When a container restarts, previous run logs, termination state, metrics, and events must be evaluated together as one cohesive body of evidence. Restart policies and probes only govern how the platform reacts; durable recovery requires pinpointing the root cause, preserving data, controlling shutdown, and verifying the workload has returned to steady serving health.

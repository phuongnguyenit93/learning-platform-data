# Configuring Container Resources

## 1. Why Does Resource Configuration Directly Affect gRPC?

In **SPRING_GRPC**, each pod/container has CPU, memory, and potentially ephemeral storage limits. A Spring Boot application running gRPC simultaneously uses the JVM heap, thread stacks, Netty event loops, direct buffers, connection pools, serializers, and database/downstream worker threads.

If the memory limit is set too low, the container can be `OOMKilled` even before the heap fills up. If the CPU limit is too tight, the JVM and Netty experience CPU throttling, increasing p95/p99 latency and causing deadlines to expire. If you only raise limits without bounding concurrency, concurrent RPCs can grow until the database pool or downstream saturates.

Resource configuration must balance three things:

- The scheduler has accurate information to place pods onto suitable nodes.
- The container has sufficient capacity for heap, native memory, threads, and concurrent load.
- The application bounds its work so it does not consume beyond pod and dependency capacity.

This lesson focuses on Kubernetes requests/limits, JVM container awareness, Netty/gRPC resources, database pools, streaming buffers, probes, graceful shutdown, autoscaling, and testing under load.

## 2. Distinguishing Requests and Limits

In Kubernetes:

- **requests** are the resource amounts the scheduler uses for placement decisions and serve as the baseline for several autoscaling algorithms.
- **limits** are the usage ceilings enforced by the runtime/kernel per resource type.
- CPU limits are enforced via quota/throttling; the container can be restricted in CPU time per period.
- Memory limits are typically enforced by the kernel OOM mechanism; processes can be killed upon exceeding the limit.
- Ephemeral storage limits govern writable layer space, logs, and `emptyDir` scoped to the container/pod per configuration.

Example:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "768Mi"
    ephemeral-storage: "256Mi"
  limits:
    cpu: "2"
    memory: "1536Mi"
    ephemeral-storage: "1Gi"
```

This is only an illustrative starting point. Do not copy numbers into production without measuring heap, native memory, thread count, traffic profile, and sidecar overhead.

A `500m` CPU request equals half a CPU core in Kubernetes units. A CPU limit of `2` allows up to roughly two cores under quota rules. Memory requests/limits are measured in bytes; `Mi` is mebibytes and `Gi` is gibibytes.

## 3. Measure All Memory, Not Just Heap

A container's memory limit applies to all memory used by the process/container, not just the Java heap. A gRPC JVM can consume:

- Heap: objects, Protobuf messages, application state, and caches.
- Metaspace: class metadata.
- Code cache: JIT-compiled native code.
- Thread stacks: each platform thread has its own stack.
- Direct/native buffers: Netty and native libraries.
- TLS/crypto buffers, allocators, and native libraries.
- Memory-mapped files and other native regions.

One way to budget:

```text
Container memory limit
  >= JVM heap budget
   + metaspace and code cache
   + thread stacks
   + Netty/direct/native buffers
   + TLS and library overhead
   + safety margin
```

If `-Xmx` is set close to the memory limit, the remaining native footprint can push the container into OOM before the heap reports `OutOfMemoryError`. Leave an ample margin based on real measurements.

Use container memory metrics, process RSS, Native Memory Tracking (where appropriate), heap metrics, and GC logs to distinguish heap pressure from native memory growth. A heap dump does not show all direct/native memory.

## 4. Make the JVM Aware of Container Limits

Modern JDKs can detect container/cgroup limits and use them for JVM ergonomics. However, behavior depends on JDK version, vendor, and flags. Verify the actual runtime rather than assuming the JVM always sees the exact CPU/RAM of the node.

You can set heap as a percentage of available memory:

```dockerfile
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0"
```

`MaxRAMPercentage` is an example; the right percentage depends on direct memory, threads, metaspace, and libraries. With a 1.5 GiB container memory limit, 60% maximum heap is only part of the budget; the remainder must still cover native memory and overhead.

When a fixed heap is needed, `-Xms` and `-Xmx` can be used, but ensure total process memory fits inside the container limit at peak load. Do not set `-Xms` too high if many replicas need to start simultaneously on memory-constrained nodes.

Inspect flags/runtime inside the container using the JVM tools appropriate for your JDK, and log the effective configuration in startup diagnostics.

## 5. Managing Netty Direct Memory and gRPC Message Buffers

gRPC Java on Netty can use direct buffers to reduce copies between the JVM heap and native I/O. These buffers live outside the regular heap yet still consume container memory.

Factors that increase direct/native memory:

- Number of connections and concurrent RPCs.
- Protobuf request/response sizes.
- Streaming messages and amount of in-flight data.
- TLS encryption/decryption buffers.
- Allocator pooling and how long buffers are retained.
- Queues holding messages awaiting processing.

Do not use heap usage as the sole proxy for memory. If heap is steady while container RSS climbs, inspect direct buffer pools, the Netty allocator, native memory, and thread counts.

You can cap direct memory via `-XX:MaxDirectMemorySize`, but do not pick a value arbitrarily. Too low a cap can cause direct buffer allocation failures under load; leaving it uncapped does not mean direct memory is free. Benchmark and observe under your exact JDK/Netty versions.

Set appropriate inbound message size and application payload limits so a single RPC cannot force a pod to hold an oversized message in memory.

## 6. CPU Limits and Their Impact on Latency

CPU requests help the scheduler place pods onto nodes with sufficient capacity. CPU limits cap the CPU time a container can consume within a quota period. When a workload needs more CPU than the limit, Linux throttles the container.

For gRPC, CPU throttling can prolong:

- Protobuf serialization/deserialization.
- TLS handshakes and record processing.
- Event-loop callbacks.
- Business logic and response mapping.
- GC/JIT and background maintenance.

Under load, throttling causes sharp latency spikes even when average CPU usage appears modest. Monitor CPU throttled time/throttled periods alongside RPC latency and `deadline exceeded`.

Do not set CPU limits overly low just to pack nodes tightly if the service is latency-sensitive. Some organizations set explicit requests and generous limits or omit CPU limits per cluster policy; the choice must align with environment quotas, fairness, and multi-tenant isolation.

## 7. Thread Pools Must Fit Within the Resource Budget

A pod may have multiple thread groups:

- Netty event loops.
- gRPC application call executor.
- Worker pools for JDBC/blocking HTTP.
- Schedulers, application task executors, and background workers.
- JVM GC, JIT, and runtime threads.

Each platform thread consumes native stack and scheduler overhead. Growing thread pools does not make the database or downstreams faster. If 100 workers simultaneously wait on 20 database connections, most threads simply hold stack memory while waiting on the pool.

Bound worker concurrency to dependency capacity. Use bounded queues and rejection/load shedding instead of unbounded queues. Avoid `CallerRunsPolicy` if tasks could end up running on transport/event-loop threads.

CPU sizing must also consider replica count. 8 CPU-heavy threads per pod across 20 pods can create 160 runnable tasks competing across the cluster.

## 8. Aligning gRPC Concurrency with the Database Connection Pool

For example, each pod has HikariCP `maximumPoolSize = 20` and the deployment scales up to 10 replicas. The database may have to serve up to roughly 200 connections from this service alone, excluding other consumers, migrations, and admin tools.

Total budget:

```text
maximum application DB connections
  = max replicas × pool maximum size
```

Do not size the pool solely for a single pod's needs. Sum across autoscaling `maximumReplicas` and database capacity.

If gRPC accepts more requests than available DB connections, requests wait for acquisition. That can tie up the call executor and exhaust deadlines before queries even begin. You should:

- Limit concurrent database work.
- Set connection acquisition timeouts aligned with remaining deadlines.
- Keep transactions short.
- Cap HPA `maxReplicas` according to the database connection budget.
- Monitor active/idle/pending connections and acquisition latency.

Adding replicas lets the application accept more RPCs but also increases total pool connections. Autoscaling must account for downstream capacity, not just CPU.

## 9. Streaming and Buffers Are Part of Memory Sizing

A stream can stay open long and hold state, observers, queues, or chunk buffers. If each stream holds 1 MiB of data and a pod has 500 concurrent streams, that alone can occupy roughly 500 MiB, excluding object overhead and transport buffers.

For streaming RPCs:

- Set message/chunk size limits.
- Use backpressure and generate messages only when downstream is ready.
- Limit concurrent streams per tenant and per pod.
- Use bounded queues instead of buffering entire streams in memory.
- Do not accumulate large files in a `ByteArrayOutputStream` or a `List`.
- Cancel producers when clients cancel or deadlines expire.
- Set maximum stream duration/idle timeouts if required by the contract.
- Use checkpoint/resume instead of keeping sessions open indefinitely.

Memory capacity must be tested with realistic concurrent stream counts, slow consumers, and network interruptions.

## 10. Kubernetes Configuration for Spring gRPC

A sample deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spring-grpc
spec:
  replicas: 3
  selector:
    matchLabels:
      app: spring-grpc
  template:
    metadata:
      labels:
        app: spring-grpc
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: example/spring-grpc:1.0.0
          ports:
            - name: grpc
              containerPort: 8443
              protocol: TCP
          resources:
            requests:
              cpu: "500m"
              memory: "768Mi"
            limits:
              cpu: "2"
              memory: "1536Mi"
```

This manifest illustrates only resources and ports. Production needs image policies, security context, secret/TLS mounts, probes, service account, network policy, and rollout strategy per platform standards.

If pods include service-mesh sidecars or log/telemetry sidecars, factor those containers' resources into pod/node capacity. Do not treat the application container as the pod's entire cost.

## 11. Readiness, Liveness, and Startup Probes

Probes control how Kubernetes routes traffic and restarts containers:

- **Startup probe:** gives the application time to start; liveness is not evaluated until startup succeeds.
- **Readiness probe:** pods receive traffic only when able to serve RPCs.
- **Liveness probe:** detects wedged processes unable to self-recover that require a restart.

gRPC health checking can use the standard health service. Example probes:

```yaml
startupProbe:
  grpc:
    port: 8443
  periodSeconds: 5
  failureThreshold: 24

readinessProbe:
  grpc:
    port: 8443
    service: ""
  periodSeconds: 5
  failureThreshold: 3

livenessProbe:
  grpc:
    port: 8443
  periodSeconds: 10
  failureThreshold: 3
```

Kubernetes gRPC probes require a compatible listener/health service and a numeric port; verify the TLS/proxy topology because native probes have configuration limitations compared to a full gRPC client. If the server requires TLS/mTLS on the health port, choose an appropriate probe mechanism instead of assuming the default probe carries client certificates.

Readiness should reflect whether the service can accept RPCs per policy. It does not necessarily have to fail merely because a secondary optional dependency temporarily errors if the service can still serve requests partially. Liveness should not depend directly on database health; a database outage is not a reason to restart every pod continuously.

## 12. Graceful Shutdown and Termination Grace Period

During rollout or scale-down, Kubernetes sends `SIGTERM` and waits `terminationGracePeriodSeconds` before force-killing. The gRPC server must stop accepting new RPCs and give in-flight calls time to complete.

A reasonable shutdown sequence:

1. Mark the instance unready to stop receiving new traffic.
2. Start graceful shutdown of servers/channels per the Spring lifecycle.
3. Let unary RPCs and active streams finish within the grace period.
4. Cancel or terminate remaining calls per policy when time expires.
5. Close executors, database pools, and other resources.
6. Exit the process before Kubernetes force-kills it.

Streams may outlive the grace period. APIs must limit stream duration or support reconnect/resume; otherwise rollouts will routinely sever streams. A `preStop` hook can help coordinate draining, though it also consumes `terminationGracePeriodSeconds`.

Do not close database pools before the application service has stopped accepting and drained requests that still need the database.

## 13. Autoscaling Must Account for Downstream Capacity

HPA typically scales on CPU or custom metrics. CPU utilization percentage is generally calculated relative to CPU `requests`; if requests are omitted or misconfigured, utilization metrics may behave unexpectedly.

CPU-only scaling can miss bottlenecks such as:

- Increasing RPC queue depth while CPU stays low because threads are waiting on I/O.
- Rising Hikari pending connections.
- Rising gRPC in-flight calls and `deadline exceeded` errors.
- Streaming sessions holding memory.
- Rising downstream latency or broker backlog.

You can add custom/external metrics like in-flight RPCs, queue depth, request rate, or pending DB acquisitions. Metrics must be stable with smoothing and thresholds to avoid scale oscillation.

Set `maxReplicas` according to the total budget of the database, broker, downstream APIs, and node capacity. If HPA scales pods beyond database capacity, the service can trigger a connection storm and widen the outage.

## 14. Observing Resources in Production

Monitor across container, JVM, gRPC, and dependencies:

| Group | Metrics to Observe |
| --- | --- |
| Container | CPU usage/throttling, memory working set/RSS, `OOMKilled`, ephemeral storage |
| JVM | Heap used/committed, GC pauses, allocation rate, metaspace, thread count |
| Netty | Direct buffer usage, event-loop lag, connections/subchannels, and transport errors |
| gRPC | In-flight RPCs, request rate, latency p50/p95/p99, status codes, stream count |
| Executor | Active threads, queue depth, queue wait, rejected tasks |
| Database | Pool active/idle/pending, acquisition time, query/lock latency |
| Kubernetes | Restarts, readiness, scheduling failures, HPA replicas, and rollout status |

When `OOMKilled` occurs, inspect container memory limit and RSS before merely raising `-Xmx`. When deadlines rise alongside CPU throttling, evaluate CPU quota. When pending DB connections rise, more pods are not necessarily the answer; the database may already be at capacity.

Set alerts on trends and saturation rather than single usage thresholds alone. Correlate traces by RPC method with resource metrics to identify which request types create pressure.

## 15. Testing Capacity and Resource Limits

Before production, run load tests in containers with resource requests/limits matching the real environment:

- Unary RPC load at increasing concurrency.
- Many requests/responses near the message size limit.
- Long-running streams, slow consumers, and cancellations.
- Database latency/lock contention and pool saturation.
- TLS handshakes/reconnects and certificate rotation.
- Intentional CPU throttling.
- Memory pressure and direct buffer growth.
- Rolling deployments while RPCs/streams are active.
- HPA scale-out/scale-in at varying load levels.

Record throughput, p95/p99, `deadline exceeded`, OOMs, GC pauses, CPU throttling, and queue depth. Identify the saturation point where adding capacity no longer improves throughput.

Local container tests do not fully replicate Kubernetes cgroups, sidecars, and node contention. Use staging/cluster tests to verify scheduler, HPA, probes, and termination behavior.

## 16. Review Checklist

- CPU, memory, and ephemeral storage requests/limits are set from measured data.
- Total memory budget includes heap, metaspace, stacks, direct/native buffers, and a safety margin.
- JVM container awareness is verified on the actual JDK.
- `MaxRAMPercentage`, `-Xmx`, and direct memory do not exceed the container budget.
- CPU throttling is monitored alongside RPC latency.
- Netty/gRPC event loops, call executors, and worker pools have bounded concurrency/queues.
- Hikari pool size is calculated against `maxReplicas` and database capacity.
- Streaming has message/chunk caps, backpressure, and concurrent stream limits.
- Readiness, liveness, and startup probes accurately reflect the lifecycle.
- Graceful shutdown includes draining and a sufficiently long termination grace period.
- HPA considers downstream/database capacity, not just CPU.
- Sidecar resources are included in the pod budget.
- Container/JVM/gRPC/executor/database metrics are correlated.
- Load tests run with production-like resource limits and rollouts.

In **SPRING_GRPC**, container resource configuration must reflect the full cost of the JVM, Netty, RPC concurrency, streaming buffers, and dependency pools. Set requests so the scheduler places pods accurately, limits sufficient for target load, and bound workers, queues, and streams to keep memory/CPU within budget. Combine probes, graceful shutdown, database-aware autoscaling, and load tests to avoid OOMs, CPU throttling, and deadline failures under load.

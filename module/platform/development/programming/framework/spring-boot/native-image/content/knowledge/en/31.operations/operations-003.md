# Memory limits and observing behavior under increasing load

## 1. Operational objectives

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring Boot applications are processed with **Spring AOT** and compiled into a **GraalVM Native Image** to improve startup time, footprint, and deployability. Once the executable is packaged into a container, the operations team needs to know how the service reacts as request rate, concurrency, and payload sizes grow.

This lesson focuses on operational decisions: setting memory requests/limits, determining headroom, observing consumption under load, recognizing saturation signals, and relieving pressure before the container gets OOM killed. Concepts such as heap, RSS, PSS, and cgroups are used as signals in dashboards and runbooks.

A service may run stably at low load yet climb rapidly in memory as concurrent requests increase. Causes may include in-flight requests holding objects, response buffers, connections, thread stacks, or temporary data; or unbounded queues, data-driven cache growth, or memory leaks. Observing only a single current memory number makes it hard for operators to distinguish normal high load from an out-of-control trend.

After this lesson, learners will be able to:

1. Choose appropriate memory requests, limits, and runtime heap budgets for native containers.
2. Build dashboards pairing memory with RPS, concurrency, queues, latency, and error rates.
3. Observe cgroup usage, process RSS, and application metrics over time.
4. Distinguish load-driven memory growth, cache warm-up, queue backlogs, and memory leaks.
5. Define alert thresholds based on headroom and growth rate rather than a single fixed percentage.
6. Bound concurrency, queues, and connection pools to control memory pressure.
7. Configure appropriate readiness, liveness, and startup probes under overload.
8. Investigate `OOMKilled`, restart loops, and memory pressure in Docker/Kubernetes.
9. Run load ramps, soak tests, and capacity reviews before increasing traffic.
10. Write response runbooks and rollback conditions for native deployments.

> **Operational principle:** memory must be observed alongside load and latency. When memory rises, identify what extra work, data, or resources the service is retaining; reduce concurrent work before simply raising the container limit.

## 2. Reading the memory curve under increasing load

When load increases in steps, service memory typically transitions through several states. The shape of the curve helps form initial hypotheses:

| Observed shape | Possible interpretation | What to check |
| --- | --- | --- |
| Rises at startup then stabilizes | Runtime, context, caches, and connection pools are initialized. | Compare idle after readiness and after warm-up. |
| Rises with RPS then plateaus | Buffers/caches/pools stabilize or concurrency is bounded. | Check queues, pool sizes, and cgroup headroom. |
| Scales with in-flight requests | Each request retains data while processing; higher concurrency means higher memory. | In-flight requests, payload size, downstream latency, and timeouts. |
| Steps up after each load wave | Caches or pools expand on demand and retain resources. | Cache size, eviction, pool max, and GC timing. |
| Grows continuously despite steady RPS/concurrency | Possible leak, accumulating queue, unbounded cache, or unreleased native allocations. | Heap after GC, queue depth, RSS, thread count, and cgroup stats. |
| Memory rises when downstream latency rises | Requests are held longer, increasing in-flight work and buffers. | DB pool wait, HTTP connection pool, retries, timeouts, and queues. |

A plateau does not automatically mean memory is safe. If the plateau sits close to the container limit, a small burst or GC peak can still get the container killed. Conversely, memory rising with load is not automatically a leak; the service may simply be holding more legitimate requests.

### 2.1. Explaining memory with concurrency

An approximate model for request memory:

~~~text
In-flight requests = arrival rate x average time in service
Request memory ~= in-flight requests x average retained bytes per request
~~~

For example, if a downstream slows down by 2x, the time a request spends inside the service increases. At the same RPS, the number of waiting/in-flight requests can nearly double. Each request holds DTOs, buffers, tracing context, and response data; memory can rise even when the request rate stays constant.

This model is only for forming hypotheses, not an exact prediction formula. Requests vary in size and execution paths; concurrency, queueing, and garbage collection also affect outcomes.

### 2.2. Distinguishing cache warm-up from leaks

Caches typically grow rapidly as the service encounters new keys/datasets, then hit their capacity bound or eviction policy. Leaks typically show a trend of retaining objects/resources even after load returns to normal.

To distinguish them:

1. Record a baseline after startup and warm-up.
2. Run a load wave of fixed duration.
3. Drop load back to idle and observe memory across multiple GC cycles.
4. Check cache size, queue depth, active connections, and thread count.
5. Repeat the same workload to see if the post-cycle baseline creeps upward.

Do not conclude a leak solely because RSS does not drop immediately after load ends. The allocator/runtime may retain allocated regions for reuse. Combine heap/object diagnostics with per-resource counters.

## 3. Setting a container memory budget

### 3.1. The memory limit applies to the entire container

In Docker or Kubernetes on Linux, memory limits are enforced via cgroups. The kernel can terminate processes when memory pressure exceeds reclaim capacity under a hard limit. A container can be OOM killed even when the Java heap has not reached `Xmx`, because the limit counts other memory regions and all processes in the same cgroup. [Docker describes hard/soft limits and OOM behavior in Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/); [Kubernetes describes cgroup-enforced memory limits and OOM kill](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).

For a native executable, set max heap below the container limit to leave room for:

- Native Image runtime and GC structures.
- Thread stacks and threads growing with load.
- Direct/network buffers.
- JNI or native libraries.
- File mappings, TLS/crypto, and client libraries.
- Logging, metrics/tracing exporters, and helper processes.
- Peaks during GC, cache warm-up, or traffic bursts.

Do not use a fixed heap-to-container ratio for every service. Measure actual peaks from representative workloads, then set max heap and container limits with verified headroom.

### 3.2. Distinguishing requests and limits in Kubernetes

- **Memory request** is used by the scheduler to decide whether a pod fits on a node; HPA also uses requests as the denominator when computing utilization for resource metrics.
- **Memory limit** is a hard limit enforced by the runtime/kernel.
- A request is not a hard cap.
- A limit is not a target the service should regularly bump against.

QoS class is determined by the resource configuration of the entire Pod. A Pod belongs to the `Guaranteed` class only when every container declares both CPU and memory requests/limits and each request equals its limit. Having one container with memory request equal to limit is not enough to conclude the whole Pod is `Guaranteed`. Evaluate QoS and eviction behavior in the context of the full Pod and cluster configuration.

Illustrative example; adjust numbers using measurements from your service:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "384Mi"
  limits:
    cpu: "1"
    memory: "512Mi"
~~~

The values `384Mi`/`512Mi` are configuration examples only, not recommended sizing for all Spring Boot Native Images. Determine requests from steady-state needs and scheduling; determine limits from measured peaks plus appropriate headroom.

### 3.3. Choosing runtime max heap

A native executable can accept heap options such as `Xms` and `Xmx` depending on the GraalVM version/runtime. For example:

~~~bash
/app/orders-service -Xms64m -Xmx256m
~~~

If the container limit is 512 MiB, a 256 MiB max heap leaves room for native/off-heap memory and other regions. Still, this number is only a starting point; if the workload uses many direct buffers, threads, or JNI, the remaining space may be insufficient.

When tuning `Xmx`:

1. Run the baseline workload and record cgroup peak.
2. Change one option at a time.
3. Monitor heap, RSS, cgroup usage, GC, and latency.
4. Run peak/soak tests.
5. Verify there are no OOMs and headroom remains as traffic increases.

Increasing heap can reduce GC pressure but may raise total memory consumption. Cutting heap too aggressively can cause frequent GC, higher latency, or allocation failures. Evaluate throughput, latency, and memory together.

### 3.4. Avoid allocating right up against the hard limit

Do not design a service where cgroup `memory.current` routinely hovers near `memory.max`. Leave space for bursts, GC, cache expansion, rolling deployments, and measurement variance. Headroom should reflect peak-to-peak variance and system availability requirements.

A simple calculation:

~~~text
Headroom bytes = cgroup memory limit - observed cgroup peak
Headroom percent = headroom bytes / cgroup memory limit x 100
~~~

Track both absolute headroom and percentage. In small containers, a given percentage may correspond to very few MiB.

## 4. Signals to observe together

Operational dashboards must correlate telemetry layers. Never make decisions based solely on heap or solely on container memory.

| Layer | Signals to monitor | Operational question |
| --- | --- | --- |
| Container | memory current, limit, peak, working set, OOM events | How much headroom remains? Is reclaim/OOM occurring? |
| Process | RSS, peak RSS, thread count, file descriptors | Which process is holding memory and OS resources? |
| Runtime | heap used/max, buffer pools, GC count/time if available | Is object allocation/GC growing with load? |
| HTTP | RPS, in-flight requests, p50/p95/p99, 4xx/5xx | Is higher load slowing requests and holding them longer? |
| Executor/queue | active threads, queue depth, rejected tasks | Is work accumulating faster than processing rate? |
| Database | active/idle connections, pending acquire, query latency | How long are requests waiting on DB and holding memory? |
| HTTP client | active connections, pending acquire, retries, timeouts | Is a downstream increasing buffers and in-flight work? |
| Cache | size, hit/miss, eviction, load time | Is memory growing from caching or abnormal retention? |
| Deployment | replica count, restarts, OOMKilled, rollout age | Is load causing restarts or uneven distribution? |

### 4.1. Spring Boot Actuator and Micrometer

Spring Boot Actuator exposes meters via Micrometer. Depending on dependencies and runtime, common groups include:

- `jvm.*`: memory/buffer pools, GC, threads, and class loading.
- `process.*`: process CPU, memory, and uptime when supported by binders/platform.
- `system.*`: CPU and system info.
- `http.server.requests`: request count and duration.
- `jdbc.connections.*` and `hikaricp.*`: connection pools.
- `executor.*` or corresponding meters for instrumented task executors/schedulers.
- `application.started.time` and `application.ready.time`: startup/ready time.

Exact meter names depend on Spring Boot, Micrometer, server, and client versions. Check the actual meter list in the running environment. [Spring Boot Metrics reference](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) documents JVM, system, startup, executor, and datasource meters.

With Native Image, do not assume every `jvm.*` meter has the same scope as on HotSpot JVM. Keep cgroup/process telemetry as the source of truth for container and process memory; use Actuator to understand application and runtime behavior where meters are available.

### 4.2. Exposing metrics safely

Example configuration for internal environments:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
~~~

An appropriate registry/exporter is required if Prometheus scrapes the service. Do not use `/actuator/metrics` as a production storage/scraping system; that endpoint is primarily for inspecting available meters and diagnostics. Use Prometheus, OpenTelemetry, or a suitable monitoring backend for time-series collection. Protect management endpoints with network policies, authentication, and organizational exposure policies.

### 4.3. Collecting cgroup metrics

On cgroup v2, monitor the primary counters:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.events
~~~

If the process lives in a sub-cgroup, determine the exact path from `/proc/self/cgroup` and mount information. `memory.events` reports counters such as `high`, `max`, `oom`, and `oom_kill`; take deltas over time intervals to see whether events occurred during a load wave.

On Kubernetes, container metrics can be collected via kubelet/cAdvisor or the cluster observability stack. Do not confuse `kubectl top`/working set with `memory.current` or RSS; label the metric source explicitly on dashboards.

## 5. Designing dashboards and alerts

### 5.1. Time-series dashboards

A minimal dashboard should align charts on a shared time axis:

1. Container memory current, peak, and limit.
2. Process RSS/peak RSS.
3. Heap used/max and GC activity if exposed by the runtime.
4. RPS and in-flight requests.
5. p95/p99 latency and error rate.
6. Executor active threads, queue depth, and rejected count.
7. DB/HTTP connection pool active, pending, and timeouts.
8. Replica count, restarts, and OOM events.

When memory rises, operators can inspect the same timestamp to see whether load, downstream latency, queues, or restarts changed before or after.

### 5.2. Alerting on headroom and growth rate

Thresholds must be calibrated with real data. Initial examples to test:

| Level | Illustrative condition | Response |
| --- | --- | --- |
| Observe | Usage rises with RPS but headroom remains and plateaus | Monitor and compare against hourly/daily baselines. |
| Warning | Sustained above ~75% of limit or rapidly shrinking headroom | Check concurrency, queues, latency, and trend. |
| Critical | Above ~85–90% of limit, rising `memory.events`, or short time-to-limit | Shed load, scale within verified capacity, prepare rollback. |
| Incident | OOM kill, restart loop, widespread request failures, or lost readiness | Trigger incident runbook and protect the rest of the system. |

These percentages are examples, not universal production thresholds. For services with naturally high peaks, warnings may be lower; for services with very stable memory, thresholds can be based on absolute headroom and growth rate.

Estimate time to limit if memory is growing steadily:

~~~text
Time to limit ~= remaining memory headroom / positive memory growth rate
~~~

This is only a short-term estimate. Memory growth is often nonlinear as caches, GC, or queues shift; use it as an auxiliary warning signal, not a guaranteed forecast.

### 5.3. Avoid single-sample alerts

A brief spike can result from GC, cache fills, or scrape timing. Combine:
- Thresholds sustained over a time window.
- Short-window growth rate.
- Remaining headroom.
- `oom`/`max` events.
- Latency/error rates and queue growth.

Alerts should distinguish "high but stable memory" from "rapidly rising memory with service degradation."

## 6. Controlled load ramping

### 6.1. Preparing before a load ramp

Before ramping load:

- Use the exact native executable and container image intended for deployment.
- Fix memory requests/limits, CPU limits, swap policy, and replica count.
- Use datasets, profiles, and downstream services close to production.
- Enable cgroup/process/application telemetry.
- Verify readiness and liveness behavior.
- Record idle and warm-up baselines.
- Define stop conditions: OOM events, headroom below safety threshold, latency/errors breaching SLO, or queues failing to drain.

Do not run load tests in shared environments without capping concurrency and total duration.

### 6.2. Stepped load ramp

Example load plan:

| Phase | Load level | Duration | Purpose |
| --- | --- | --- | --- |
| Baseline | 10% of target load | 5 min | Establish idle/warm memory. |
| Step 1 | 25% | 5–10 min | Observe initial changes in memory and latency. |
| Step 2 | 50% | 10 min | Observe queues, pools, and GC. |
| Step 3 | 75% | 10 min | Identify where saturation begins. |
| Step 4 | 100% | 15–30 min | Validate target load. |
| Burst | 125% briefly | 1–3 min | Verify burst absorption and recovery. |
| Recovery | 10% or idle | 10 min | Verify queues/caches/resources return to steady state. |

Levels and durations are examples. Adjust to SLOs, traffic patterns, and risk tolerance. Stepping up gradually pinpoints where memory or latency begins rising nonlinearly.

### 6.3. Measure concurrency and queues, not just RPS

A service can receive the same RPS yet exhibit different memory usage when:
- Payloads are larger.
- Downstreams are slower.
- Request timeouts are longer.
- Retries amplify downstream call counts.
- Queues allow more requests to wait.
- Connection pools are congested.

Record in-flight requests, queue depth, active threads, connection acquire wait, and downstream latency. When these rise alongside memory, locate where work is being held back.

### 6.4. Running soak tests

Hold steady load long enough to observe:
- Cache growth and eviction.
- Thread/connection leaks.
- Queues failing to drain back to zero after load drops.
- Memory baseline creeping upward after each cycle.
- GC frequency and pause times.
- Cgroup memory peak and OOM events.

A short test only proves the service survives a brief burst; it does not prove memory stability over many hours.

## 7. Throttling load to protect memory

When memory rises alongside concurrency or queues, reducing the work retained inside the process is often more effective than immediately raising limits.

### 7.1. Bounding concurrency

Set appropriate limits for:
- Concurrent in-flight requests.
- Worker threads and task executors.
- DB and HTTP client connections.
- Parallel batch tasks.
- In-flight messages being processed.

Limits must coordinate with downstream throughput. For example, increasing web concurrency while keeping the DB pool small may simply cause more requests to wait on connections and hold objects longer.

### 7.2. Using bounded queues

Unbounded queues can accumulate requests faster than they are processed. Use bounded queues and define full-queue behavior:
- Reject tasks early.
- Return appropriate HTTP 429 or 503 responses.
- Apply `Retry-After` if clients can honor it.
- Offload work to an external durable queue if business semantics allow.
- Emit rejected/queue-full metrics for observability.

Do not use huge queues to mask downstream bottlenecks. Large queues usually trade immediate errors for long latency and memory pressure.

### 7.3. Timeouts, retries, and bulkheads

- Set connect/read/response timeouts according to SLOs.
- Use bounded retries with exponential backoff and jitter.
- Do not retry endlessly when a downstream is failing.
- Separate pools for dependencies with different criticality.
- Use bulkheads so one slow downstream cannot occupy all workers.
- Avoid holding request bodies or response buffers longer than necessary.

A retry storm can amplify in-flight requests, connection usage, and memory right when the service is already starved for resources.

### 7.4. Payload limits and streaming

Large payloads can scale memory with concurrent requests. Consider:
- Capping request body size.
- Validating `Content-Length` and handling chunked bodies properly.
- Streaming files/large responses instead of buffering them completely if APIs/frameworks support it.
- Bounding upload concurrency.
- Avoiding unnecessary payload copies across layers.
- Using pagination for large result sets.

## 8. Readiness, liveness, and startup probes under memory pressure

The three probes serve distinct roles:

- **Startup probe:** lets the application finish initialization before kubelet begins liveness/readiness checks.
- **Readiness probe:** decides whether the pod receives traffic through the Service; can transition the pod to not-ready during overload or recovery.
- **Liveness probe:** determines whether the process is stuck/unable to progress and needs a restart.

Do not configure liveness probes to fail solely due to high memory utilization or temporary latency spikes. If every pod restarts under high load, remaining pods absorb extra traffic and can trigger cascading failures. Kubernetes warns that misconfigured liveness probes can cause restarts under load and destabilize systems. [Kubernetes probe guidance](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/).

Example probes:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 30

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
~~~

This is an illustrative configuration; choose timeouts, periods, and failure thresholds based on startup duration and recovery capability. Health groups must be exposed/configured properly for your Spring Boot version. Readiness can remove a pod from traffic when temporarily overloaded, but there must be a recovery path back to Ready. Do not tie readiness checks to a non-essential downstream if doing so would drop all replicas from the Service.

## 9. Autoscaling and memory limits in Kubernetes

### 9.1. Memory utilization can be a lagging signal

HPA can scale on resource metrics such as CPU or memory utilization; utilization is calculated relative to resource requests. However, memory often does not drop immediately when traffic falls because caches or allocators retain allocated regions. Consequently, scaling on memory alone can:
- Scale out during cache warm-up rather than genuine capacity shortage.
- React too slowly when request backlogs surge rapidly.
- Keep replica counts inflated after load subsides.
- Miss a hot container if looking only at aggregate pod usage.

Kubernetes HPA also supports container resource metrics and custom/external metrics depending on version/adapters. Choose signals closer to the cause of overload—such as CPU, RPS per pod, in-flight requests, or queue depth—while using memory as a safety guard. [Kubernetes HPA documentation](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/).

### 9.2. Do not use autoscaling as a substitute for backpressure

Scaling out reduces load per replica, but it cannot fix:
- Unbounded queues.
- Retry storms.
- Misconfigured connection pools.
- Unbounded caches.
- An already saturated downstream.
- Per-replica memory leaks growing over time.

Combine autoscaling with concurrency caps, queue bounds, and timeouts. Cap `maxReplicas` according to database, broker, and downstream capacity.

### 9.3. Example Deployment resources and native heap

~~~yaml
containers:
  - name: orders
    image: registry.example.com/orders:native
    command: ["/app/orders-service"]
    args: ["-Xmx256m"]
    resources:
      requests:
        cpu: "500m"
        memory: "384Mi"
      limits:
        cpu: "1"
        memory: "512Mi"
~~~

This is a syntax example. Before applying, confirm that the native executable accepts the runtime `Xmx` option for your GraalVM version and replace illustrative numbers with load-test results. If the chart/entrypoint uses a wrapper script, verify how arguments are forwarded to the native process.

## 10. Runbook when memory rises rapidly

### 10.1. Confirm blast radius

Check immediately:
- Cgroup current/limit/peak and event counters.
- Container restart count, `OOMKilled`, exit codes, and pod events.
- Count of Ready/NotReady replicas.
- RPS, in-flight requests, p95/p99 latency, and error rates.
- Queue depth, rejected tasks, and connection pool wait times.
- Downstream latency, timeouts, and retry rates.

Do not look only at aggregate dashboards; identify which pods/containers are climbing rapidly and whether all replicas are affected.

### 10.2. Classify the cause

| Observation | First hypothesis | Inspection action |
| --- | --- | --- |
| Memory rises with in-flight requests | Concurrency too high or slow downstream | Inspect request duration, DB/HTTP pool wait, and timeouts. |
| Queue grows continuously | Consumers/workers cannot keep up with producers | Throttle producers, bound queues, check consumer throughput. |
| Heap grows with cache size | Cache expanding with keys/data | Check max size, TTL, eviction, and key cardinality. |
| Heap is stable but RSS grows | Native/direct buffers, threads, or JNI | Inspect process maps, thread count, and library metrics. |
| Cgroup rises while app RSS is stable | Page cache, kernel, sockets, or other processes | Inspect cgroup `memory.stat` and process list. |
| One replica grows abnormally | Traffic skew, hot key, or local leak | Compare per-pod request rates, routes, tenants, and age. |
| Memory rises after each rollout | Cache warm-up or dependency/config change | Compare startup timelines and build/versions. |

### 10.3. Pressure-relief actions

In priority order depending on the situation:

1. Reduce or rate-limit incoming traffic if the system has a rate limiter/gateway.
2. Lower concurrency and batch parallelism to previously verified safe levels.
3. Enable bounded queue/rejection behavior if a backlog is building.
4. Pause non-essential or deferrable batch workloads.
5. Scale out if downstreams and the cluster still have capacity.
6. Increase memory limits only when telemetry proves legitimate demand and nodes have sufficient resources.
7. Roll back the release if a memory regression appeared after deploy.
8. Capture logs, cgroup events, and diagnostic artifacts before restarting if conditions allow.

Do not disable the OOM killer to hide the problem. Do not raise limits beyond node capacity or downstream database capacity. Do not restart all replicas simultaneously when rolling replacements can be done sequentially.

### 10.4. After the service stabilizes

- Save the timeline of memory/load/latency/queues and events.
- Compare before/after lowering concurrency or rolling back.
- Identify whether memory grew due to requests, caches, threads, pools, or native allocations.
- Create a reproducible load test.
- Set regression thresholds for peak memory and latency.
- Update memory requests/limits and autoscaling policies based on data.
- Document temporary mitigations versus permanent fixes.

## 11. Rollout and capacity review

Before releasing a new native executable:

1. Compare RSS/cgroup peak against the currently running version under the same workload.
2. Review max heap, GC, and runtime flags.
3. Run startup/ready, steady load, burst, and soak tests.
4. Verify requests/limits and node allocatable capacity.
5. Verify startup/readiness/liveness probes.
6. Roll out a canary with a limited traffic percentage.
7. Monitor per-pod memory, latency, errors, and restarts.
8. Increase traffic only while all signals stay within thresholds.
9. Keep a baseline image/version ready for rollback.

If the canary shows a different memory slope or queue growth than the baseline, halt the rollout and hold traffic at the current level. Do not wait for an OOM to conclude a release has a regression.

### 11.1. Capacity per replica

Determine sustainable load per replica via load testing. Choose an operating point below the onset of saturation to leave room for bursts and pod replacements. Calculate replica counts from peak traffic and capacity per replica, while verifying total connection pools do not exceed database capacity.

If each pod opens up to 30 DB connections and the deployment runs 20 replicas, the database can receive up to 600 connections from this service alone. Autoscaling must align with downstream connection budgets.

### 11.2. Rolling deployments and node memory headroom

During a rolling update, old and new pods coexist temporarily. Nodes need enough allocatable memory for surge replicas alongside existing workloads. If nodes lack memory, rollouts may remain `Pending` or put pressure on other pods.

Set `maxSurge`, `maxUnavailable`, resource requests, and node capacity according to realistic rollout plans—not just steady-state replica memory.

## 12. Hands-on lab: observing a native service under rising load

**Context:** a Spring Boot native service runs in Kubernetes with a `512Mi` memory limit. As load increases, p99 latency and `memory.current` rise together; several pods get `OOMKilled`. The team must find the root cause and reconfigure load throttling.

### Tasks

1. Record GraalVM/JDK, Spring Boot, native build options, image, resource requests/limits, and replica count.
2. Capture startup, ready, and idle baselines across process/cgroup/application metrics.
3. Run a stepped load ramp at 10%, 25%, 50%, 75%, and 100% of target load.
4. Record memory current/peak/limit, RSS, heap/buffer metrics, in-flight requests, and p95/p99.
5. Record executor queues, active threads, DB/HTTP connection pools, pending acquires, and retry rates.
6. Identify where saturation begins and the maximum load that still meets SLOs.
7. Re-run with elevated downstream latency to inspect memory driven by in-flight requests.
8. Configure bounded queues, concurrency limits, timeouts, and retry policies.
9. Verify readiness/liveness behavior under pod overload; ensure liveness does not trigger restart cascades.
10. Run burst and soak tests; observe whether memory plateaus and recovers.
11. Compare CPU/custom-metric HPA with memory guards; verify database capacity.
12. Write a runbook covering alerts, mitigations, rollback, and conditions for raising memory limits.

### Evidence log

| Evidence | Contents to record |
| --- | --- |
| Runtime | GraalVM/JDK, Spring Boot, GC, and runtime options. |
| Container | Image, requests/limits, cgroup version, and node allocatable capacity. |
| Baseline | Idle/ready memory, heap, RSS, cgroup, and startup time. |
| Workload | Request mix, RPS, concurrency, payload size, duration, and downstream latency. |
| Saturation | Point where queues/latency/errors/memory begin rising nonlinearly. |
| Controls | Concurrency, queue capacity, timeouts, retries, pool sizes, and rate limits. |
| Scaling | HPA metrics, min/max replicas, per-pod capacity, and DB connection budget. |
| Probes | Startup/readiness/liveness config and overload test outcomes. |
| Incident | OOM events, restart reasons, mitigations, and rollback timeline. |
| Decision | New limit/heap budget, headroom, and supporting test evidence. |

### Completion criteria

- [ ] Distinguishes memory requests from hard limits.
- [ ] Dashboard pairs memory with RPS, in-flight requests, latency, and queues.
- [ ] Identifies whether memory growth comes from concurrency or resource retention.
- [ ] Measures cgroup peak and OOM events during load tests.
- [ ] Identifies where saturation begins.
- [ ] Enforces concurrency caps and bounded queues.
- [ ] Timeouts/retries do not trigger retry storms.
- [ ] Readiness and liveness probes serve distinct roles.
- [ ] HPA cannot overwhelm database/downstream capacity.
- [ ] Reserves headroom for bursts and rolling deployments.
- [ ] Runbook clearly states mitigations, rollback, and criteria for raising limits.

## 13. Self-assessment questions

1. Why can memory increase when RPS stays constant while downstream latency rises?
2. How do you distinguish cache warm-up from a memory leak?
3. How does a Kubernetes memory request differ from a memory limit?
4. Why must `Xmx` be lower than the container memory limit?
5. Which metrics should share the same dashboard to explain memory pressure?
6. Why do bounded queues control memory better than unbounded queues?
7. When should you lower concurrency instead of raising the memory limit?
8. How does a readiness probe differ from a liveness probe when a service is overloaded?
9. Why can autoscaling on memory alone react slowly or inaccurately?
10. What must be checked before scaling out to avoid overloading the database?
11. Why do rolling deployments require node memory headroom for surge replicas?
12. What evidence should be preserved after an `OOMKilled` incident?

## 14. Official references

Meter names, resource behavior, and probe semantics depend on framework and platform versions. Cross-check against your exact deployment versions:

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): JVM/system/startup metrics, executors, HTTP clients, and datasource instrumentation.
- [Spring Boot — Actuator Metrics Endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/metrics.html): inspecting available meters for diagnostics; do not use this endpoint as a production metrics backend.
- [Docker Engine — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/): hard/soft memory limits, swap, and OOM behavior.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): requests, limits, cgroup enforcement, and `OOMKilled`.
- [Kubernetes — Horizontal Pod Autoscaling](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/): resource, container, and custom metrics for autoscaling.
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): how kubelet uses probes to restart containers or stop routing traffic.
- [GraalVM Native Image — Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/): runtime heap/GC options and memory limits of native executables.

**Key takeaway:** as load grows, memory usually rises alongside concurrency, queues, and how long requests remain inside the service. Observe these signals together with cgroup headroom, throttle work via explicit bounds, and change memory limits only after measurements establish the root cause and platform capacity.

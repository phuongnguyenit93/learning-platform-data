# Selecting Capacity Based on CPU, Memory, and Network Requirements

In the **Container Hosting Services** chapter, capacity selection means determining how much CPU, memory, and network capacity each container needs to handle load with the appropriate latency, availability, and cost. Capacity must be derived from workload characteristics and measured metrics. Under-provisioning causes throttling, OOMs, or network bottlenecks; over-provisioning increases cost and can make it harder for the scheduler to place workloads onto nodes.

This lesson falls within the scope of **CLOUD_CORE_SERVICES_COMPUTE**: exploring cloud compute capacity models—from virtual machines and containers to serverless—learning how to select CPU, memory, networking, and security settings, and practicing deployment, load scaling, ensuring availability, and optimizing operational cost.

## 1. Translating Application Requirements into Capacity Metrics

Before choosing a service type or container size, describe the workload using verifiable metrics:

| Requirement Area | What to Collect | Significance for Capacity Selection |
|---|---|---|
| Traffic | Average, p95, peak requests/second, and peak duration | Determines replica count and burst tolerance |
| Concurrency | In-flight requests, open connections, queues | Impacts memory, threads, and connection pools |
| Latency | p95/p99 SLOs, CPU processing time, and I/O wait time | Determines headroom and bottleneck locations |
| Data | Request/response sizes, payloads, files, or streams | Estimates throughput and buffer memory |
| Dependencies | Databases, caches, internal services, external APIs | Accounts for east-west traffic and downstream limits |
| Operations | Availability targets, startup time, scale-out speed | Decides minimum replica count and redundancy |

Measure under production-representative load, including peak periods. A low CPU reading while the application is waiting on a database does not prove the container has ample capacity; similarly, low average RAM can mask memory spikes when many requests run concurrently.

At a minimum, collect:

- CPU usage per container and node, CPU throttling, or CPU wait time.
- Working set and memory utilization per container; restart counts and OOMKilled events.
- Request rate, concurrency, p50/p95/p99 latency, error rate, and queue depth.
- Ingress/egress bytes, throughput, connection count, retransmissions, timeouts, and load balancer/NAT errors.
- Replica count, scale-out time, startup time, and node allocation percentage.

## 2. Estimating CPU

CPU is calculated from the actual processing time required per unit of work. For an API, you can estimate required cores with:

\[
\text{Required CPU cores} =
\text{requests/second} \times
\text{CPU seconds/request}
\]

This is the average CPU demand at the target traffic level. If you want to maintain a target utilization \(u\), the provisioned capacity needs to be approximately:

\[
\text{Provisioned CPU cores} =
\frac{\text{Required CPU cores}}{u}
\]

For example, an API handles 250 requests/second and profiling shows each request consumes 18 ms of CPU:

\[
250 \times 0.018 = 4.5\ \text{CPU cores}
\]

If you target about 65% CPU utilization to leave headroom for variance, total required capacity is:

\[
4.5 / 0.65 \approx 6.93\ \text{vCPU}
\]

You can start testing with roughly 7–8 total vCPUs, then tune based on actual load test results and redundancy requirements. This is an initial estimate, not a performance guarantee: CPU time per request varies with data, cache hit rates, algorithms, TLS, garbage collection, and library calls.

### Choosing vCPUs per Replica

Total CPU can be divided into many small replicas or fewer large replicas:

- Many small replicas generally enable finer-grained scale-out and limit the blast radius when one replica fails. In return, total overhead from runtimes, sidecars, connections, and memory can increase.
- Fewer large replicas reduce copy counts and can suit workloads needing many threads or parallel processing. In return, scale-out is coarser, and each replica startup or replacement has a larger impact.
- CPU-bound workloads such as encryption, compression, image processing, or computation require profiling to select core counts and parallelism levels. Raising thread counts past useful core counts can increase context switching.
- I/O-bound workloads typically spend significant time waiting on networking or storage. Simply adding CPU may not improve throughput; check connection pools, downstream limits, and I/O latency.

### Requests, Limits, and Throttling in Kubernetes

In Kubernetes:

- **resources.requests.cpu** is the CPU amount the scheduler uses to place Pods onto nodes and serves as the basis for relative CPU shares during contention.
- **resources.limits.cpu** sets the maximum CPU cap. When a container hits its quota, processes can be throttled even when the node has idle CPU.
- Total Pod requests, plus system overhead, must fit within the node's allocatable capacity. Do not treat a node's advertised total vCPU count as capacity fully available to applications.

Setting requests too low can cause the scheduler to overpack Pods onto nodes and create contention. Setting limits too low can increase throttling and p99 latency. Compare CPU usage, throttled time, and latency before adjusting requests/limits. On serverless container platforms, check how the provider allocates CPU during request handling, while idle, and during startup.

## 3. Estimating Memory

Memory must cover the entire working set of processes inside the container, not just the heap or business data. One budgeting formula per replica is:

\[
\begin{aligned}
\text{Estimated memory} ={}&
\text{runtime baseline} \\
&+ \text{memory for concurrent requests} \\
&+ \text{caches and buffers} \\
&+ \text{native memory, thread stacks, and overhead}
\end{aligned}
\]

Then add headroom based on observed variance. Remember to include sidecars if they run in the same Pod and count toward Pod/node resource limits.

For example, an API has a 300 MiB runtime baseline, up to 20 concurrent requests at roughly 20 MiB per request, a 250 MiB cache, and 200 MiB for native memory/stacks/buffers:

\[
300 + (20 \times 20) + 250 + 200 = 1{,}150\ \text{MiB}
\]

If you want this estimate to stay under roughly 75% of the container limit:

\[
1{,}150 / 0.75 \approx 1{,}534\ \text{MiB}
\]

A 2 GiB limit is a reasonable starting point for testing in this example. Re-measure the working set at peak concurrency, with warmed caches, and during deployment/startup.

Key points to keep in mind:

- Memory does not elastically compress like CPU. Exceeding the cgroup limit can cause the kernel to terminate the container and Kubernetes to record `OOMKilled`.
- **requests.memory** influences Pod scheduling decisions; **limits.memory** is the container's memory ceiling. Setting requests much lower than the working set increases the risk of node memory pressure.
- For the JVM, the heap is not the container's entire memory footprint. Leave room for metaspace, direct buffers, thread stacks, JIT, and native libraries. You can configure the heap as a percentage of container RAM, then validate against RSS/working set metrics.
- For cache-heavy applications, verify eviction policies and cache size limits. Caches boost hit rates but also consume memory; never let caches grow unbounded.
- If a Pod runs multiple containers, sum their requests and review per-container limits. Sidecar proxies, log agents, and telemetry also consume resources.

## 4. Estimating Network Capacity

Network capacity encompasses throughput, latency, concurrent connections, and new connection establishment rate. For an API, you can estimate data bandwidth with:

\[
\text{Throughput (bytes/s)} =
\text{requests/s} \times
(\text{request bytes} + \text{response bytes})
\]

For example, each request averages 10 KiB inbound and 200 KiB outbound. At 250 requests/second:

\[
250 \times 210\ \text{KiB} \approx 51.3\ \text{MiB/s}
\]

That equals roughly 430 Mbit/s of aggregate application data. With a 1.5x traffic burst, throughput can approach 645 Mbit/s. This calculation excludes protocol overhead, TLS, retransmissions, health checks, telemetry, and calls to downstream dependencies. When evaluating real network paths, separate ingress and egress directions because limits can differ.

Check network limits specific to each service tier:

- Maximum bandwidth per instance, task, node, NIC, or underlying machine type.
- Throughput limits of load balancers, NAT gateways, API gateways, and cross-zone links.
- Concurrent connections, connection tracking, ephemeral ports, and new connection rate.
- Cross-zone/cross-region latency and data transfer costs across zones or out to the Internet.
- Payload sizes, MTU, TLS termination, keep-alive, connection pooling, and retry policies.
- Network policies, firewalls, and service meshes can constrain paths or add overhead; having valid network access does not guarantee sufficient bandwidth.

If the application frequently calls databases or internal APIs, include service-to-service traffic. Excessive retries can amplify network and downstream load during incidents. Prefer keep-alive, connection pooling, bounded timeouts, and retries with backoff and jitter.

## 5. Combining CPU, Memory, and Network into One Configuration

Never size capacity based on a single metric in isolation. A replica can handle load only if CPU, memory, and network paths are all sufficient. For example, spare CPU with maxed-out memory still triggers OOMs; spare memory with saturated network throughput still drives up timeouts.

Selection workflow:

1. Define target load, peak load, concurrency, and latency SLOs.
2. Profile CPU time per request to estimate total required cores.
3. Measure the working set at target concurrency, adding caches, native memory, and overhead.
4. Calculate ingress/egress from payload sizes and traffic; verify per-instance and end-to-end path limits.
5. Choose replica counts and per-replica sizing that retain headroom when a replica or node becomes unavailable.
6. Test ramping load, bursts, scale-out, scale-in, and slow downstream scenarios.
7. Tune based on metrics, cost, and SLO results.

### Combined Example: Product Catalog API

Suppose an API has the following characteristics measured in staging:

| Parameter | Assumed Value |
|---|---:|
| Sustained peak load | 250 requests/second |
| CPU time per request | 18 ms |
| Target CPU utilization | 65% |
| Baseline memory | 300 MiB |
| Memory per concurrent request | 20 MiB |
| Maximum concurrency to test | 20 |
| Cache | 250 MiB |
| Native memory, stacks, and buffers | 200 MiB |
| Average inbound + outbound payload | 210 KiB/request |

Initial estimates:

- CPU: \(250 \times 0.018 / 0.65 \approx 6.93\) vCPU. With a 1 vCPU replica, the load matching the 65% target is around \(0.65 / 0.018 \approx 36\) requests/second. Seven replicas handle nearly 250 requests/second on average; choose 8 replicas at peak load for extra headroom and tolerance against losing one replica.
- Memory: expected working set is 1,150 MiB. Applying the headroom calculation above, begin testing with a 2 GiB limit per replica.
- Network: each replica at roughly 36 requests/second generates nearly 60 Mbit/s of bidirectional application data. With a 1.5x burst, verify each instance's network path sustains around 90 Mbit/s or more, while also checking aggregate egress, NAT, and load balancer limits.

An initial test configuration could be 8 replicas, each with 1 vCPU and 2 GiB RAM. You can set `minReplicas` lower to save cost during low traffic, but you must measure scale-out time and cold starts to establish the floor. The example below uses Kubernetes; the numbers are a starting point for load testing, not a default configuration for every application.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 8
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: api
          image: registry.example.com/catalog-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
            limits:
              cpu: "1"
              memory: "2Gi"
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: catalog-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: catalog-api
  minReplicas: 4
  maxReplicas: 16
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
~~~

The HPA in this example uses CPU as its scaling signal. If the application is bottlenecked by network, concurrency, or queues, CPU may stay low while latency climbs. In that case, add appropriate custom/external metrics—such as request concurrency, queue depth, or throughput—while ensuring the cluster autoscaler can provision nodes when Pods go unscheduled. Kubernetes does not automatically allocate additional bandwidth just because HPA adds more Pods.

In managed container services or serverless containers, map the same calculations to maximum CPU/RAM per instance, maximum concurrency, min/max instances, and network limits published by the provider. For task-based platforms like Fargate or container apps, check allowed CPU/memory combinations, per-task/instance limits, startup times, and billing models. For self-managed Kubernetes, add kubelet, DaemonSet, system component, and sidecar overhead when calculating node allocatable capacity.

## 6. Operational and Cost Trade-Offs

| Decision | Benefit | Trade-off to Monitor |
|---|---|---|
| Increase CPU per replica | Handles more parallel work when CPU-bound | Higher per-replica cost; wasted if the app is I/O-bound |
| Increase replica count | Distributes load, improves fault tolerance and scale-out | Increases overhead, downstream connections, and load balancer/NAT costs |
| Increase memory | Reduces OOM risk, accommodates larger working sets/caches | Higher cost; high requests can reduce Pod density on nodes |
| Increase concurrency | Utilizes resources while requests wait on I/O | Increases memory, connections, and pressure on databases |
| Use autoscaling | Tracks load and reduces capacity during off-peak hours | Introduces scale lag; requires minimum capacity and spare node headroom |
| Use larger instance/network tier | Can boost throughput and connection limits | May pay higher fees even when underutilized |

Track cost per unit of work, such as cost per 1,000 successful requests or per hour of batch processing. If increasing CPU lowers latency but successful request count stays flat because the database is already bottlenecked, that change yields no net efficiency gain. Tuning connection pools, queries, caches, or workload distribution can deliver better results than upsizing containers.

## 7. Post-Deployment Verification

Perform these checks in staging or a load-capped canary rollout:

1. Record CPU/memory request and limit configs, replica counts, node allocatable capacity, instance network limits, and downstream service limits.
2. Ramp load through average, sustained peak, and burst levels. Hold each level long enough to observe autoscaling, caching, and garbage collection.
3. Track CPU usage alongside CPU throttling; verify whether Pods are pending due to insufficient CPU or nodes face resource contention.
4. Track working set, RSS/heap if applicable, peak memory, restarts, and OOMKilled events.
5. Track directional ingress/egress, throughput, concurrent connections, DNS/TLS errors, timeouts, retransmissions, and NAT/load balancer limits.
6. Compare p95/p99, error rates, and queue depth against SLOs. Identify which resource hits its threshold first when load increases.
7. Simulate losing a replica or node, scale-out/scale-in, and rolling out a new version. Confirm remaining replicas still satisfy target load.
8. Document results, update requests/limits, min/max replicas, and alerts. Repeat whenever application versions, payloads, or traffic patterns change.

Basic verification commands on Kubernetes:

~~~bash
# View CPU and memory usage of nodes and Pods
kubectl top nodes
kubectl top pods -n production

# Check scaling status and replica counts
kubectl get deployment,hpa,pods -n production
kubectl describe hpa catalog-api -n production

# Check Pods that are resource-throttled or OOMKilled
kubectl describe pod <pod-name> -n production
kubectl get events -n production --sort-by=.lastTimestamp

# Check remaining allocatable capacity on nodes
kubectl describe nodes
~~~

The `kubectl top` command requires Metrics Server and primarily shows point-in-time usage; it does not replace historical metrics, CPU throttling, p95/p99 latency, or network telemetry. Use your platform's monitoring system or Prometheus/OpenTelemetry to view trends and correlate resources with SLOs. For network throughput, gather metrics from container/host, CNI, load balancer, and cloud network telemetry; never infer bandwidth solely from CPU or Pod count.

Do not run load generators or `iperf3` in production without an approved testing window and traffic cap. A network test must measure the actual production path without disrupting shared services.

## 8. Capacity Selection Checklist

- [ ] Defined average, p95, peak, and burst request rates, concurrency, and SLOs.
- [ ] Profiled CPU time per request and calculated total vCPUs against target utilization.
- [ ] Selected replica counts based on per-replica load, scaling behavior, and loss of a replica/node.
- [ ] Budgeted baseline memory, concurrent requests, caches, native memory, sidecars, and headroom.
- [ ] Verified requests/limits and node allocatable capacity; accounted for CPU throttling and OOM risks.
- [ ] Calculated ingress/egress from payloads and checked throughput, latency, connections, NAT, load balancers, and downstream limits.
- [ ] Configured autoscaling with reasonable min/max bounds and verified node capacity can scale along with it.
- [ ] Load-tested sustained load, bursts, scale-out, scale-in, and failure scenarios.
- [ ] Correlated metrics against p95/p99, error rates, availability, and cost per unit of work.
- [ ] Recorded baselines, alert thresholds, and triggers for re-evaluating capacity.

Good capacity is a configuration verified under representative load, carrying enough headroom for variance, and backed by measured metrics. Whenever the application or traffic changes, re-measure CPU time, working set, and network throughput to update the configuration rather than keeping container sizes unchanged out of habit.

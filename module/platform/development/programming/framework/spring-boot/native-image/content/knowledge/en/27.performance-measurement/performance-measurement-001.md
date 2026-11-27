# Defining Goals Before Comparing JVM and Native

## Lesson Objectives

Compiling a Spring Boot application into a **GraalVM Native Image** can reduce startup time and memory consumption for certain workloads. However, a native executable is not faster than the JVM on every metric by default. A long-running application with steady load that is optimized by the JVM JIT may have different throughput or latency than native; native also comes with build costs, compatibility requirements, and its own operational workflow.

Therefore, before benchmarking, you need to clearly define what the system aims to improve and which conditions remain constant. A useful measurement must answer an operational or business question, such as reducing scale-out time, increasing container density per node, lowering memory limits, or reducing costs for a specific workload.

This lesson helps you:

- Translate the motivation for using Native Image into measurable goals and hypotheses.
- Choose a workload representative of how the Spring Boot application is actually deployed.
- Identify metrics for startup, memory, throughput, latency, CPU, and cost.
- Distinguish between cold start, warm-up, and steady-state.
- Design a fair, repeatable comparison between JVM and native.
- Set decision criteria before looking at benchmark results.

## 1. Start from the Problem to Solve

### 1.1. Native Image Is an Architectural Choice

Native Image changes how an application is built and run. With Spring Boot, Spring AOT prepares bootstrap code and metadata; GraalVM Native Image performs reachability analysis and compiles an executable for the target platform.

Commonly sought benefits:

- Faster process startup in environments that frequently create new instances.
- Lower memory footprint in certain applications and workloads.
- Higher number of instances per node when memory is the primary constraint.
- Suitability for short-lived, scale-to-zero, or rapid scale-out workloads.

Costs and trade-offs to factor into the decision:

- Native compilation generally takes more build time and build resources.
- The binary depends on the target OS, CPU architecture, and native libraries.
- Some libraries or dynamic behaviors require reachability metadata, Runtime Hints, or design changes.
- Steady-state performance can differ from a warmed-up, JIT-optimized JVM.
- Debugging, profiling, observability, and release workflows need to be verified on native.

Do not choose native solely because of a startup number in an example or a small executable size. Determine whether that benefit actually improves the real system.

### 1.2. Write Goals as Measurable Questions

A good goal has three components: **subject**, **metric**, and **conditions**.

Examples:

| Need | Benchmark Question |
|---|---|
| Slow scale-out | Does native reduce the time from process creation to readiness under the same container configuration? |
| Node running out of RAM | Does native reduce RSS at target load and increase the number of replicas per node? |
| Short-lived workload | Does native process the same number of requests over a short lifecycle at a lower total cost? |
| Steady-load API | Does native keep throughput and p95/p99 latency within SLO thresholds after warm-up? |
| Infrastructure cost | Under the same workload and SLO, how does compute cost per successful request change? |
| Slow build pipeline | Does native compilation time impact release cadence or CI costs? |

These questions differ and can lead to different conclusions. A native executable might win on readiness but fail to meet throughput requirements for a continuously running API.

### 1.3. Define Priorities and Acceptance Thresholds

Before running a benchmark, record:

- The most important metric.
- Current SLOs or system thresholds.
- Minimum meaningful improvement.
- Maximum acceptable regression in secondary metrics.
- Whether additional build and operational costs are acceptable.

For example, a goal could be reducing RSS at target load by at least 20% while keeping throughput degradation under 5% and p95 within SLO. These numbers are only examples to illustrate threshold setting; use your system's actual metrics and budget.

## 2. Choosing a Representative Workload

### 2.1. Classify by Application Lifecycle

First, determine which group the application belongs to:

| Workload Type | Characteristics | Typically Important Metrics |
|---|---|---|
| Short-lived job | Starts, processes a small amount of work, and exits | Startup, total completion time, peak memory |
| Scale-to-zero service | May have zero instances for periods of time | Cold start, readiness, first-request latency |
| Bursty API | Traffic arrives in bursts; replicas scale up/down on demand | Startup, scale-out time, latency during load spikes |
| Long-running API | Runs continuously with relatively steady load | Throughput, p95/p99, CPU, memory, GC |
| Memory-constrained service | Limited by RAM or pod density | RSS, peak memory, replicas/node |
| Background worker | Consumes messages or jobs over long periods | Processing throughput, queue lag, memory, shutdown |

Do not use a single synthetic workload to represent every application type. If production involves both cold-start and steady-state, measure both modes separately.

### 2.2. Describe the Workload with Quantitative Metrics

Record at minimum:

- Requests/messages per second and distribution over time.
- Read/write request ratio and payload sizes.
- Number of tenants, data types, and dataset size.
- Cache hit/miss ratio.
- Number of connections to databases, caches, message brokers, and external services.
- Concurrency level and how clients generate load.
- Average lifetime of an instance.
- Minimum/maximum replicas and how the autoscaler behaves.

If no production trace is available, use a workload synthesized from contracts/APIs and anonymized data. Document all assumptions so others can reproduce the measurement.

### 2.3. Choose Load Scenarios

A baseline set of scenarios:

1. **Cold start:** launch a new process and measure until readiness.
2. **First request:** send the first request after readiness to uncover lazy initialization costs.
3. **Warm-up:** ramp load gradually to give the JVM time for JIT compilation.
4. **Steady-state:** hold steady load long enough to observe throughput, latency, and memory.
5. **Burst:** rapidly increase concurrency to observe responsiveness under sudden load spikes.
6. **Soak:** run long enough to observe memory growth, cache, queue, and GC behavior.
7. **Scale-out/scale-in:** create and stop instances following realistic deployment scenarios.

Not every application needs all seven scenarios. Select the scenarios matching the goals defined at the beginning.

## 3. Forming Hypotheses for JVM and Native

### 3.1. The JVM Baseline Must Be Properly Configured

Comparing native against a JVM running with default settings may not reflect a production setup. The JVM may need:

- Heap sizing appropriate for the container memory limit.
- A GC suited to target latency/throughput.
- Sufficient warm-up to JIT-compile hot paths.
- Appropriate CPU quota and thread counts.
- Connection pool and cache configurations matching the deployment environment.

Document the JVM vendor/version, flags, and resource limits. You can run two baselines: the JVM with its current production configuration and a tuned JVM within the same resource budget. This clarifies which operational state native is being compared against.

### 3.2. Native Must Also Be Built and Run Properly

A native executable is affected by:

- GraalVM version and Native Image build options.
- Target OS, CPU architecture, and builder/container image.
- Profiles, feature flags, and Spring AOT configuration.
- Reachability metadata, Runtime Hints, and resource configuration.
- Optimization and build-time initialization options.
- How memory limits, CPU quotas, and environment variables are configured at runtime.

Do not compare a tuned JVM against a misconfigured native build or one running the wrong workload. Conversely, do not tune native by changing many factors at once and attributing the entire result to the compiler.

### 3.3. Write Hypotheses Before Running

Example:

```text
Goal: reduce the API memory footprint in a 512 MiB container.

Hypotheses:
- Native has lower steady-state RSS than JVM.
- Native still achieves at least 800 requests/second throughput.
- p95 latency does not exceed 150 ms at target concurrency.
- Readiness time decreases enough to improve scale-out.

Conditions:
- Same source revision, dependencies, and business configuration.
- Same database/cache, dataset, CPU quota, and memory limit.
- JVM gets warm-up; native is measured on both cold-start and steady-state.
```

This is an illustrative example, not guaranteed numbers. Every hypothesis needs a measurement, a pass threshold, and a corresponding workload.

## 4. Selecting Metrics to Measure

### 4.1. Startup and Readiness

Distinguish these milestones:

- **Process start:** the moment the OS starts the process.
- **Application started:** Spring Boot completes the startup phase reported by the framework.
- **Readiness:** the application is actually ready to serve traffic according to the readiness probe.
- **First request:** timing and latency of the first request.

Readiness matters more than the process appearing. An application may have opened its port without yet connecting to the database, warming caches, or being ready to handle business logic.

Measure at least:

```text
startup_to_ready_ms = ready_timestamp - process_start_timestamp
first_request_latency_ms =
    first_response_timestamp - first_request_timestamp
```

If startup requires connecting to external services, keep those services in the same state across runs. You can also measure Spring internal startup time and dependency wait time separately to distinguish framework overhead from environment overhead.

### 4.2. Memory

Do not equate heap with total memory footprint.

| Metric | Meaning |
|---|---|
| JVM heap used/committed | Heap currently in use and heap allocated by the JVM |
| RSS / working set | Memory pages of the process currently resident in RAM as reported by the OS |
| Peak RSS | Highest RSS observed during the measurement window |
| Container/cgroup memory | Memory accounted against container limits and cgroup accounting |
| JVM native memory | Metaspace, code cache, thread stacks, direct buffers, and other off-heap regions |
| Post-warm-up memory | Footprint once the application has processed the workload and reached a steady state |

The JVM has many off-heap regions; comparing `heap used` directly against native RSS is unfair. Compare metrics with equivalent meaning, prioritizing RSS/container memory when the question is how many instances can run on a node.

Measure memory at readiness, after warm-up, during steady-state, and at peak under burst/soak. Caches, thread pools, connection pools, and in-flight payloads can cause memory to grow after startup.

### 4.3. Throughput and Latency

Record:

- Throughput: successful requests per second.
- p50: median latency.
- p95 and p99: tail latency.
- Error rate and timeout rate.
- First-request latency and post-warm-up latency.

Do not look at average latency alone. One variant with a low average but high p99 can degrade user experience and violate SLOs.

Keep payload, request mix, concurrency, and test duration identical. Use a load generator capable of producing stable load; avoid letting the load generator itself become the bottleneck.

### 4.4. CPU and Resource Efficiency

Measure CPU usage or CPU-seconds per batch of successful requests. If native uses less RAM but significantly more CPU, overall cost might not decrease.

Useful metrics:

```text
cpu_seconds_per_1000_success =
    process_cpu_seconds / successful_requests * 1000

memory_per_replica =
    aggregate_steady_state_rss / replica_count
```

For a single process, replica_count equals 1. When comparing multiple replicas, use the exact same measurement method and per-replica load.

### 4.5. Build and Operational Metrics

Native Image also incurs non-runtime costs:

- Native compilation time.
- CI CPU/memory consumed during builds.
- Executable and container image size.
- Image pull and rollout time.
- Rebuild frequency when dependencies or target platforms change.
- Cost of maintaining metadata/hints and compatibility testing.

If the application releases frequently or targets multiple platforms, build time and pipeline capacity can be the deciding factor. Do not leave these costs out of the overall evaluation.

## 5. Defining Success Criteria

### 5.1. Do Not Optimize Every Metric at Once

Metrics involve trade-offs:

- Reducing startup may not improve steady-state throughput.
- Lowering RSS may come with higher CPU or latency.
- Increasing concurrency may boost throughput while worsening p99.
- Reducing memory per replica may allow higher pod density, but database connections or downstream capacity may become the new bottleneck.

Choose one primary metric and guardrails. For example:

| Goal Type | Primary Metric | Guardrails |
|---|---|---|
| Scale-out | Readiness time | First-request latency, error rate |
| Memory density | RSS/container memory | Throughput, p95/p99, CPU |
| Long-running API | Throughput or p95 | p99, error rate, memory |
| Short-lived job | Total completion time | Correct output, peak memory |
| Cost efficiency | Cost/successful request | SLO, capacity, and build cost |

### 5.2. Calculate System-Level Benefits

If memory per replica decreases, calculate the benefit against node limits and shared resources. For example, theoretical memory-bound replica count:

```text
memory_limited_replicas =
    floor((node_memory - reserved_memory) / memory_per_replica)
```

This is only the RAM limit. Actual replica count also depends on CPU, database connections, network, file descriptors, scheduler overhead, and the autoscaler.

For cost, you can compare:

```text
cost_per_success =
    total_compute_cost / successful_requests
```

Include instance cost, runtime duration, retries, errors, build pipeline, and operations if they have meaningful impact. Do not conclude cost savings from lower memory alone.

### 5.3. Set Stopping Thresholds

Before benchmarking, agree on disqualifying conditions:

- Error rate exceeds threshold.
- p95/p99 violates SLO.
- Throughput falls below minimum.
- Peak memory exceeds container limit.
- CPU exceeds budget or causes throttling.
- Native build is unstable or lacks support for a required dependency.

If a variant fails a guardrail, do not use gains in the primary metric to mask that failure.

## 6. Designing a Fair Comparison

### 6.1. Hold Non-Experimental Factors Constant

| Factor | How to Control |
|---|---|
| Source code | Same commit/tag |
| Dependencies | Same versions and lockfile |
| Spring configuration | Same business properties and corresponding profile |
| Database/cache/broker | Same version, dataset, and state |
| CPU | Same model, quota, and pinning if any |
| Memory | Same container/cgroup limit |
| Network | Same topology and latency to dependencies |
| Load | Same request mix, payload, concurrency, and duration |
| Observability | Same log/metrics/tracing overhead level |

If native requires a separate profile/AOT variant, document that difference and ensure equivalent business logic.

### 6.2. Separate Cold-Start from Steady-State

Do not start the JVM, immediately measure a single request, and compare it with native in the same bucket without explanation. The JVM may need warm-up to JIT-compile hot paths; native may have different startup behavior without the same JIT mechanism.

Run two groups:

1. **Cold-start benchmark:** spawn a fresh process per run, measuring process-to-readiness and first request.
2. **Steady-state benchmark:** run the same warm-up workload for both variants, then measure over a stable window. The JVM can JIT-compile hot paths during this phase; native does not have a JVM-style JIT but may still complete lazy initialization, populate caches, or establish connections.

If production frequently scales to zero, cold-start carries high weight. If processes run for days, steady-state may matter more.

### 6.3. Repeat and Alternate Ordering

Run multiple independent iterations. Alternate JVM/native ordering or randomize runs to reduce effects from:

- CPU temperature and throttling.
- Filesystem/page cache.
- Background load on the host.
- Pre-warmed database/cache state.
- Network jitter.
- JIT compilation and GC timing.

Record median, percentiles, and variance. If the difference between two results is smaller than measurement noise, there is insufficient evidence to declare one variant better.

### 6.4. Avoid Skewed Benchmarks Caused by the Load Generator

The load generator must have enough CPU/network capacity to generate the target load. Use the same machine or machine type for load generation; if the load generator shares a node with the application, document it because CPU contention can skew results.

For latency tests, choose the right load model:

- Closed-loop: the client sends the next request after the previous one completes; concurrency is bounded.
- Open-loop/rate-based: the client attempts to send requests at a fixed rate; suited for observing queueing when the system is overloaded.

Closed-loop can hide latency spikes under high load because the send rate drops as response time slows. Open-loop requires tracking queues and dropped requests. Use the same model when comparing both variants.

## 7. Recommended Benchmark Workflow

### Step 1 — Write a benchmark brief

Record goals, workload, hypotheses, primary metric, guardrails, and success thresholds. Only start measuring once stakeholders agree on evaluation criteria.

### Step 2 — Prepare both variants

Build the JVM artifact and native executable from the same source/dependencies. Record Java/GraalVM version, build arguments, profile, target OS/CPU, and build time.

### Step 3 — Verify functional equivalence

Run the same contract/integration tests on both variants. Confirm endpoints, transactions, caching, async processing, serialization, resources, and business outcomes match before measuring performance.

### Step 4 — Run cold-start

Spawn a fresh process per run. Measure process start, application started, readiness, and first request. Keep dependency state identical.

### Step 5 — Run steady-state and burst

Run the same request mix and concurrency through the chosen warm-up period for both variants. Then measure throughput, p50/p95/p99, CPU, RSS, peak memory, and error rate. Record JVM warm-up duration separately to observe JIT effects.

### Step 6 — Run soak and shutdown

Run long enough to detect memory growth, queue accumulation, cache behavior, and GC. Then measure shutdown and verify tasks/connections close cleanly.

### Step 7 — Synthesize and decide

Compare results against hypotheses and guardrails. Calculate replica/node-level gains or cost/request. Document unfavorable results, variance, and measurement limitations.

## 8. Benchmark Brief Template

Use the template below before taking measurements:

```text
Application:
- Service name:
- Source revision:
- Spring Boot version:
- JVM version / GraalVM version:
- Target OS / CPU architecture:

Goals:
- Current problem:
- Priority metric:
- Minimum improvement:
- Guardrails:

Workload:
- Workload type:
- Request/message rate:
- Request mix and payload:
- Concurrency:
- Dataset and dependencies:
- Instance lifetime:

Environment:
- CPU quota:
- Memory limit:
- Database/cache/broker:
- Network topology:
- Observability overhead:

Methodology:
- Cold-start iterations:
- Warm-up duration:
- Steady-state duration:
- Burst/soak scenarios:
- Load generator and model:

Results to record:
- Readiness time:
- First-request latency:
- Throughput:
- p50 / p95 / p99:
- RSS / peak RSS / container memory:
- Heap / GC / CPU:
- Error rate:
- Build time / image size:

Decision:
- Criteria passed:
- Criteria failed:
- Outcome:
- Limitations and next steps:
```

## 9. Examples of Choosing Goals for Two Service Types

### 9.1. Scale-to-Zero API

Suppose an API only receives traffic during certain hours and can scale to zero replicas off-hours. The primary goal is reducing the time from when the autoscaler creates a container until readiness succeeds.

Scenario:

1. Scale the service down to zero replicas.
2. Send a request to trigger scale-up.
3. Record pod/process creation time and readiness time.
4. Send the first request and measure latency/errors.
5. Repeat multiple times with identical dependency state.

Primary metrics are scale-to-ready and first-request latency. Measure scheduling/image pull time as well if the goal is end-to-end experience; if measuring only process startup, isolate orchestration overhead from the measurement.

Native may fit if reducing cold start improves the SLO sufficiently. However, if most of the wait time is image pull, database connection, or the scheduler, speeding up Spring initialization may yield only a small improvement.

### 9.2. Continuously Running API Under Steady Load

For a continuously running API, the JVM can warm up and JIT-compile hot paths. The goal might be reducing memory to increase replica density while keeping throughput and p99 within thresholds.

Scenario:

1. Run JVM and native with identical CPU/memory limits.
2. Warm up the JVM for the specified duration and workload.
3. Increase concurrency in fixed steps.
4. Hold each step long enough to stabilize.
5. Record throughput, p95/p99, CPU, RSS, and error rate.
6. Find the maximum load at which both still meet SLOs.

If native lowers RSS but drops throughput beyond the threshold, calculate whether higher replica density offsets the extra instances or CPU required.

## 10. Conclusions to Avoid

| Hasty Conclusion | Why Evidence Is Insufficient |
|---|---|
| Native is always faster than JVM | Results depend on cold-start, JIT warm-up, workload, and configuration |
| Lower native RSS means more efficient heap | RSS and heap are two different metrics |
| Faster startup log means faster readiness | Dependencies, health checks, and lazy initialization may still be running |
| One first request represents steady-state | JVM has warm-up and JIT; phases must be measured separately |
| Native uses less RAM so total cost is lower | CPU, replica count, network, build, and operational costs also matter |
| Successful native build means valid benchmark | Functional equivalence and workload equivalence must still be verified |
| A single run is enough to conclude | System noise and caches can skew results |

## 11. Pre-Benchmark Checklist

- Is the goal tied to a specific operational or business problem?
- Have a primary metric and guardrails been chosen?
- Does the workload reflect request mix, concurrency, and instance lifetime?
- Are cold start, first request, warm-up, and steady-state separated?
- Is the JVM baseline sensibly configured and warmed up for steady-state measurements?
- Is the native executable built for the exact target OS/CPU?
- Are source, dependencies, profile, dataset, and dependency services equivalent?
- Is the memory comparison looking at heap, RSS, or container memory consistently?
- Does the load generator have enough capacity and use the same load model?
- Are there enough iterations to evaluate variance?
- Are stopping thresholds set for error rate, p95/p99, throughput, CPU, and peak memory?
- Are build time, image size, and operational costs factored into the decision?

### Self-Check Questions

1. Why should goals be defined before choosing a benchmarking tool?
2. When is readiness time more important than the application-started time reported by Spring?
3. Why must cold-start and steady-state be measured separately?
4. Why can you not compare JVM `heap used` directly against native RSS?
5. If a native service reduces memory but increases CPU and p99 latency, how should it be evaluated?
6. Why must workload, dependencies, and resource limits be held constant during comparison?
7. When can native compilation costs change the deployment decision?

**Key takeaway:** start with a system goal, then choose an appropriate workload, metrics, and guardrails. Measure readiness, memory, throughput, latency, CPU, and cost by phase; keep comparison conditions consistent and repeat measurements. Choose Native Image only when observed benefits solve the application's actual problem while still meeting functional, SLO, and operational requirements.

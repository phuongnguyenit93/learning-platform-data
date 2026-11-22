# Designing Measurements with Equivalent Load, Repetition, and Environment Control

Evaluating CRaC performance is only meaningful when measurements compare two launch approaches under equivalent conditions. If a cold-start run uses a busy CPU, cold database, and heavy load while a restore run executes on an idle node with a warm cache, the results do not reveal the true benefit of the checkpoint. Conversely, if only JVM restore time is measured while omitting image pull, volume mount, dependency reconnection, and readiness, the results may fail to reflect the deployment time that operators care about.

A reliable benchmark must clearly define the question to answer, measure each phase separately, use the same workload and offered load, repeat multiple times, control the environment, record every discrepancy, and analyze variance. With CRaC, at least three questions should be separated: how much faster restore makes the application ready, whether the first request after restore is faster, and whether steady-state performance under the same load changes.

There is no single number representing "CRaC performance". Checkpoint creation time, restore time, deploy-to-readiness time, first-request latency, throughput, CPU, memory, and storage cost answer different questions. Good measurement design must state clearly where each metric starts/ends and which conditions are held constant.

## 1. Defining the Question and Measurement Scope

Before running a benchmark, write a testable hypothesis. For example:

- Restoring from a checkpoint reduces the time from container launch until readiness succeeds.
- Warm-up saved in the checkpoint reduces the latency of the first 100 requests.
- Once both runs reach steady state, throughput and p95 are nearly identical.
- Restore increases initial memory usage or storage read time.
- When scaling 20 replicas simultaneously, CRaC reduces time-to-ready but creates a database connection burst.

Each hypothesis requires its own set of metrics and workflow. Do not merge everything into a single benchmark and pick the most favorable numbers.

### Three Main Measurement Groups

| Group | Question | Key Measurement Points |
|---|---|---|
| Startup/restore | How fast is the application ready to serve? | Process start/restore invocation to readiness; deploy-to-ready if infrastructure is included |
| First-request | Do the first users after restore pay initialization cost? | First-request latency and latency distribution of the first N requests |
| Steady-state | When running steadily under equivalent load, how do the two modes differ? | Throughput, p50/p95/p99, error rate, CPU, allocation, GC, memory, and dependency load |

Beyond these three groups, checkpoint creation cost, artifact size, push/pull time, volume mount/copy time, and operational cost can be measured separately. These metrics are important when calculating total benefit across the pipeline and production.

### Defining the Clock Scope

A single "startup time" figure can include or exclude multiple phases. Give each interval its own name:

```text
T_deploy_to_ready
  = scheduling
  + image pull
  + volume attach/mount
  + init container / checkpoint copy
  + process launch or restore
  + reconnect dependency
  + readiness checks

T_process_to_ready
  = process launch / restore invocation
  + runtime and application startup
  + reconnect dependency
  + readiness checks

T_ready_to_first_success
  = time from readiness until the first successful request
```

If the goal is to evaluate deployment experience, measure `T_deploy_to_ready`. If the goal is to compare runtimes, also measure `T_process_to_ready`. If the checkpoint is placed inside an image layer while cold start already has the image cached on the node, state explicitly whether image pull is included. Do not compare two numbers with different scopes.

## 2. Establishing the Baseline and Test Groups

The baseline is the execution mode used for reference. For CRaC applications, there are usually at least two groups:

- **Cold start:** launching the application from the selected artifact and runtime, performing normal startup.
- **CRaC restore:** restoring from a checkpoint created from the same application build and a compatible runtime.

If warm-up benefit needs to be evaluated, document which warm-up suite the checkpoint was created after. An unwarmed checkpoint may only skip part of initialization; a post-warm-up checkpoint may also contain reusable internal JIT/cache state.

Do not use different builds for the two groups. Keep identical:

- Application JAR/container image and source commit.
- JDK vendor, version, build, JVM options, and GC configuration.
- Static application configuration and feature flags.
- Dataset, fixtures, request mix, and response size.
- Database, broker, cache, and dependent service versions.
- CPU/memory limits, thread count, replica count, and network path.
- Load generator version and benchmark script.

If one group must use a different configuration to create the checkpoint, explicitly document the difference and treat it as an experimental variable. Do not silently change heap, GC, thread pools, or pool sizes between the two groups.

### Separating Checkpoint Effectiveness from Checkpoint Creation Cost

There are two perspectives:

1. **Runtime benefit:** comparing only the time and resources from process/restore start until readiness.
2. **Lifecycle cost:** accounting for build, warm-up, checkpoint creation, storage, image/volume distribution, and restore.

If a checkpoint is reused across hundreds of scale-outs, the one-time creation cost can be amortized over many restores. If the checkpoint must be recreated frequently or contains rapidly staling data, preparation cost can be significant.

Example general formula:

```text
total_cost_crac(N) =
    checkpoint_build_cost
    + checkpoint_storage_and_distribution_cost
    + N * restore_cost

total_cost_cold(N) =
    N * cold_start_cost
```

This is a conceptual model; actual cost can be measured in time, CPU-seconds, compute/storage/network currency, or a combination. Report both one-time cost and per-launch cost.

## 3. Designing Identical Workloads

Both groups must receive the same set of requests following the same distribution. "Same number of requests" does not necessarily mean "same load": 10,000 cache-read requests have a different cost from 10,000 database-search requests or requests serializing large payloads.

Define the workload using these attributes:

- Ratio of each route/use case.
- Payload shape, request size, and response size.
- Cache hit/miss ratio.
- Success rate, valid error rate, and retry rate.
- Tenant, user role, or feature flags that alter code paths.
- Dependency call frequency and number of queries per request.
- Run duration and request sending rate.
- Concurrency, bursts, and start times of each scenario.

### Example Request Mix

Suppose an order-processing service has the following workload:

| Scenario | Request Share | Payload/Execution Path |
|---|---:|---|
| Read order details | 40% | Small/medium response, involves cache and repository |
| Search orders | 25% | Filtering, sorting, pagination, and database query |
| Check payment status | 15% | Calls dependent service or cache |
| Update shipping details | 10% | Validation and database write in test fixture |
| Valid error paths | 5% | Not found, validation error, or permission denied |
| Large payload | 5% | Multi-item list or large response |

These shares are examples only. Derive the distribution from access logs, traces, or validated load models. Use synthetic/anonymized data and resettable fixtures. If there are side effects, run in an isolated environment and restore state between trials.

### Preserving Data and Cache State

Cache is a variable that easily skews benchmarks. If the CRaC image contains a warm cache while the cold-start test reads a cold database, the measurement may reflect cache state rather than restore benefit. This can be a valid objective when measuring a post-warm-up checkpoint, but it must be explicitly documented.

Separate test modes should be used:

- **Cache-neutral:** reset/standardize caches before each trial to compare runtime overhead.
- **CRaC-warm-cache:** allow internal caches retained by the checkpoint to persist; cold-start is warmed up under the same policy before measuring steady state.
- **Production-realistic:** simulate the exact cache state expected during scale-out, including distributed caches and database buffer caches.

Do not mix results from these modes in the same table without distinguishing them. Document which caches reside in the heap, which reside outside the process, and which are reset between trials.

## 4. Equivalent Load: Offered Load, Concurrency, and Burst

There are two commonly used load generation models:

- **Open-loop:** the load generator sends requests at a target rate, independent of previous response times. This model is suited for evaluating a system under a fixed offered load and detecting queueing/overload.
- **Closed-loop:** a fixed number of virtual users/clients send the next request only after the previous request finishes. This model is suited for evaluating fixed concurrency, though the sending rate drops when the server slows down.

Neither model is right for every question. When comparing latency at the same arrival rate, open-loop is usually easier to interpret. When comparing performance with a fixed number of workers/clients, closed-loop can be appropriate. Use the same model for both cold start and CRaC restore.

### Why Setting Only the Same Number of Virtual Users Can Be Misleading

In a closed-loop test, when the server slows down, clients wait longer before sending the next request. The system receives fewer requests precisely when it is slow. This can mask tail latency, a phenomenon commonly known as *coordinated omission*.

Open-loop with a predefined arrival rate reveals requests arriving while the server is busy. However, the load generator must have sufficient capacity and monitor its own queue; if the generator cannot sustain the target rate, the result no longer reflects the intended offered load.

### Example with k6 Constant Arrival Rate

The following example uses the `constant-arrival-rate` executor to generate open-loop load. The same script file and same fixtures should be used for both groups:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_load: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300'],
  },
};

const baseUrl = __ENV.BASE_URL;

export default function () {
  const response = http.get(`${baseUrl}/api/orders/benchmark-order-001`);
  check(response, {
    'status is 200': (r) => r.status === 200,
  });
}
```

The rate, duration, VU, and threshold values are examples only. Adjust them according to system capacity, ensuring `preAllocatedVUs`/`maxVUs` are sufficient to produce the offered load without turning the generator into a bottleneck. If there are multiple routes, select routes by fixed probabilities or use seeded scenario data so both groups receive the same distribution.

### Checking the Load Generator

The load generator must run on a machine or node independent of the server under test, with sufficient CPU/network and without sharing significant resources with the application. Monitor the generator's CPU, network, dropped iterations, VU saturation, and queue. If the generator saturates, do not conclude that the server has reached maximum throughput.

## 5. Separating Startup, First Request, and Steady State

This is the most important point when evaluating CRaC. Measuring only steady state after a few minutes can miss the biggest benefit of warm-up saved in the checkpoint. Measuring only the first request leaves performance after stabilization unknown.

### Experiment A: Startup/Restore to Readiness

Measure from the defined starting milestone until readiness succeeds. Do not send business traffic during this measurement, except for the health/readiness probes the system actually uses.

Record separately:

- Container/Pod scheduling time.
- Image pull time.
- Volume attach/mount or checkpoint copy time.
- JVM launch/restore time.
- CRaC `afterRestore()` callback duration.
- Dependency reconnect duration.
- Time until the readiness probe transitions to ready.

If the benchmark runs directly on a VM without container orchestration, inapplicable stages may be omitted, but keep the definitions identical between both groups.

### Experiment B: First Request After Readiness

Once readiness becomes true, immediately send the first representative request according to a fixed rule. Measure latency from both the client and server sides if possible. Continue measuring an initial sequence of requests—for example, requests 1, 5, 10, 50, and 100—to observe how cold-path overhead diminishes.

Do not run a hidden warm-up pass before measuring the first request. If the system requires a health check that populates caches or loads classes, document it because it can alter results. Health probes should be identical between both groups.

### Experiment C: Steady State Under Equivalent Load

For the steady-state question, put both groups through the same stabilization phase before starting the measurement window. This phase must use the same duration, request mix, and offered load. Then measure over a fixed window, for example 5–15 minutes depending on the workload and stability.

Note: additional warm-up for cold-start in Experiment C reduces the initial difference between the two groups. This is intentional because the question here is steady performance after both have warmed up. Do not use Experiment C results to draw conclusions about first-request latency.

### Experiment D: Burst and Scale-Out

If production frequently launches multiple replicas simultaneously, measure the burst scenario separately. Start a set of replicas on the same schedule, with the same dependencies and offered load. Observe image pull/volume reads, CPU, connection creation rate, database sessions, consumer rebalances, and the time until all replicas reach readiness.

Do not extrapolate single-replica results to scale-out results. CRaC can shorten per-instance startup time while creating concurrent load on storage or dependencies if many replicas restore at the same time.

## 6. Controlling Hardware and Operating System Environment

JVM performance depends strongly on the environment. Keep fixed or document every variable that may affect results.

### CPU

- Use the same CPU type or the same node pool/instance family.
- Record model, architecture, microcode, and relevant instruction flags.
- Keep the same CPU quota, cpuset, and number of available cores.
- Avoid running heavy background tasks or other benchmarks on the same node.
- If possible, keep the same CPU governor and frequency scaling policy.
- Record throttling in cgroup/container.

CPU frequency, thermal throttling, and noisy neighbors can alter latency significantly. One group running during high CPU turbo while another runs while hot/throttled will yield skewed results.

### Memory and NUMA

- Keep the same memory limits/requests and heap sizing.
- Record RSS, heap used/committed, native memory, and page faults.
- Keep the same NUMA policy or the same instance type if NUMA has an impact.
- Avoid letting one group experience memory pressure or swapping while the other does not.
- Record OOM kills, container evictions, and cgroup memory events.

CRaC restore can exhibit different memory/page fault characteristics compared to cold start. Do not compare `-Xmx` alone; examine RSS, native memory, and page-in duration if the checkpoint is large.

### Disk and Filesystem

- Use the same storage type and filesystem when comparing.
- Record checkpoint size, read speed, IOPS, and latency.
- Identify whether the page cache is warm.
- If the checkpoint resides in an image layer, record whether the image was pre-pulled/cached or whether pull is included.
- If the checkpoint resides on a volume, keep the same storage class, mount options, and node topology.
- Avoid letting one trial run on local SSD while another reads from a network filesystem.

### Network

- Use the same network path, MTU, TLS policy, and DNS resolver.
- Keep the same distance to the load generator and dependencies.
- Record latency/loss/retransmissions if the network could have an impact.
- Do not run one group on the same node network while the other traverses a cross-zone path.

### Kernel and Container Runtime

Record the kernel version, container runtime, cgroup version, CRIU/JDK CRaC build, and relevant system limits. Checkpoint/restore can depend on these components. When comparing cold start with CRaC, keep the runtime image and node pool as compatible as possible; if CRaC requires a distinct environment, explicitly document that as a mandatory requirement of the approach.

## 7. Controlling JVM and Application Configuration

Keep the same JVM options between cold-start and the checkpoint builder, except for mandatory differences that must be explicitly documented. Parameters that typically need locking:

- `-Xms`, `-Xmx`, and heap limits.
- GC algorithm and GC tuning flags.
- Thread stack size and processor count visible to the JVM.
- JIT/compiler flags and tiered compilation.
- System properties and timezone.
- Classpath/module path and native library path.
- Logging level and tracing/metrics instrumentation.
- Thread pools, connection pools, and queue limits.

Do not change `availableProcessors`, pool sizes, or GC for only one group to make the benchmark look better. If the goal is to optimize each option with its best configuration, conduct a separate tuning experiment and report all changed settings.

### Logging and Instrumentation

Synchronous logging, detailed tracing, profilers, and metrics exporters can add overhead. Keep the same instrumentation level between both groups. If a profiler is needed for diagnostics, run a separate pass and do not mix profiler results with primary benchmark results.

Do not disable logging in one group while keeping logging in the other. Likewise, do not enable debug logging to troubleshoot during final performance trials. If startup logs need to be recorded, use the same configuration and record log volume.

## 8. Controlling Dependency State

Applications typically depend on databases, caches, brokers, DNS, identity providers, and HTTP services. These dependencies can fluctuate during measurement.

Maintain:

- The same version and configuration of databases/brokers/caches.
- The same dataset, indexes, schema, and transaction isolation.
- The same connection pool limits and timeouts.
- The same network path, TLS, and credential policy.
- The same cache state or the same reset/warm procedure.
- The same background load and the same number of other clients using the dependency.

If a dependency is shared across multiple trials, run in a controlled order and reset necessary state between trials. Avoid letting a cold-start trial warm up the database buffer cache immediately before a CRaC trial without recording it.

### Dependency Reconnection After Restore

CRaC may require closing connections before checkpoint and creating new connections after restore. This can slow down `afterRestore()` and readiness. Measure reconnection time, new connection count, and retry errors separately. If cold start also opens new connections, use the same database conditions and connection pool configuration.

If many replicas restore simultaneously, the database can experience a connection storm. Measure a single replica and a scale-out batch separately; do not use single-replica results to represent a cluster.

## 9. Controlling Page Cache and Cache State

The OS page cache, image layer cache, application cache, and database cache are distinct layers. They can create major differences across trials.

Before each trial, clearly decide which state is needed:

- **Warm filesystem cache:** the image/checkpoint has been read beforehand; appropriate when production nodes normally keep images in cache.
- **Cold filesystem cache:** needed when measuring a fresh node or when the checkpoint must be read from cold storage.
- **Warm application cache:** internal caches have been populated via warm-up and may be contained inside the checkpoint.
- **Cold application cache:** reset caches to measure startup/first access.
- **Warm dependency cache:** database/cache servers already hold commonly used data.

Do not arbitrarily clear the page cache on production nodes or run privileged commands solely to create a cold trial. If measuring a cold filesystem cache is required, use a separate test node/VM or create an isolated environment according to operational policy. Record the method and cache state.

With CRaC, a checkpoint may read pages from file-backed mappings or require page-ins from checkpoint storage depending on how the runtime/OS persists state. Measure both restore duration and page faults/I/O when investigating causes. Do not infer behavior solely from checkpoint size.

## 10. Repeating Experiments and Randomizing Order

A single run is insufficient to draw conclusions. Latency can vary with CPU frequency, GC timing, background jobs, network jitter, and dependency state.

A practical workflow:

1. Run a pilot to verify scripts, validate the load generator, and obtain a preliminary estimate of variance.
2. Determine the trial count and measurement window before collecting official results.
3. Run multiple independent trials for each group; 5–10 trials can work for initial screening, while noisy workloads or critical decisions require more trials.
4. Randomize or alternate the cold/CRaC order so one group does not always run first or last as nodes warm up.
5. When possible, use paired runs on the same node/host within close time windows.
6. Reset fixtures, caches, or dependency state per protocol before each trial.
7. Save raw results and metadata for every trial.
8. Repeat failed trials according to a predefined policy; do not delete outliers merely because the results look unfavorable.

Example alternating order:

```text
Block 1: CRaC -> Cold
Block 2: Cold -> CRaC
Block 3: Cold -> CRaC
Block 4: CRaC -> Cold
Block 5: random order
```

The order must be chosen in advance or randomized using a recorded seed. If each trial requires a fresh node, pair them by matching node type and system load timeframe.

### Why Paired and Randomized?

Paired runs reduce the effect of differences across nodes or time windows. Randomized order reduces bias from environmental drift over time. Always running cold first and CRaC second can allow database cache, image cache, or CPU temperature to benefit the second group.

Do not run cold and CRaC concurrently on the same node if they compete for CPU/memory/disk and interfere with one another. If running concurrently on two nodes, ensure both nodes are equivalent and do not contend on shared dependencies.

## 11. Sample Size and Statistical Analysis

The required number of trials depends on variance and the magnitude of difference you want to detect. Do not pick the trial count merely for convenience.

A practical approach:

- Use a pilot run to estimate median, variance, and spread across trials.
- Define the minimum operationally meaningful improvement, such as a 10% reduction in time-to-ready or 50 ms at p95.
- Choose enough trials so that the confidence interval of the difference is narrower than the decision threshold.
- If results are noisy, increase trial count or improve environment control before drawing conclusions.

### Reporting Median and Confidence Intervals

For startup time, typically report the median across trials along with min/max or a confidence interval. For request latency, report p50/p95/p99 within each measurement window and the distribution across trials. Bootstrapping can be used to estimate confidence intervals for medians or percentiles when distributions are non-normal.

Do not merely take the mean across all requests while ignoring run-to-run variation. If one trial has a very high p95 due to a slow dependency, retain and investigate it according to protocol. Exclude a trial only when predefined exclusion criteria are met—such as the load generator crashing or the node experiencing OOM—and report the number of excluded trials alongside the reasons.

### Percentiles Require Sufficient Samples

p99 from a few hundred requests is unstable. To estimate tail latency, gather enough observations and report the actual request count. If the workload is short, p99 may reflect only a handful of samples. Extend the measurement window or explicitly state that the percentile is insufficiently reliable.

### Do Not Pool Data Across Different Modes

Do not pool first-request latency with steady-state latency. Do not mix cache-cold and cache-warm runs. Do not mix trials executed on different CPUs without stratification. If an aggregate figure is required, explain how it is computed and still provide per-group data.

## 12. Metric Definitions and How to Measure Them

### Startup/Restore Duration

Measure using timestamps from an external controller or process supervisor so measurements do not depend on the application's internal clock. Record the milestones:

- `t0`: defined launch/restore start.
- `t1`: process created or restore command started.
- `t2`: post-restore JVM/application callback begins.
- `t3`: required dependencies are ready.
- `t4`: readiness succeeds.

From these, `t4 - t0`, `t4 - t1`, `t3 - t2`, and other intervals can be computed. Use a monotonic clock within the same controller to measure durations; if timestamps span multiple hosts, account for clock skew.

### Request Latency

Measure from the load generator to reflect actual caller wait time, including network round trips. Server-side timing can be added to distinguish queueing/network/application time. Use the same client, timeouts, TLS, connection reuse, and network path for both groups.

### Throughput and Offered Load

Record both the request rate the generator intended to send and the rate the server actually completed. A system showing low throughput because the load generator sent slowly is not server-limited. Report error rate, dropped iterations, and timeouts alongside throughput.

### CPU and Memory

Collect CPU utilization/throttling, RSS, heap used/committed, native memory, GC pause/count, allocation rate, thread count, and page faults. Measure within the same time window and the same cgroup/container boundary.

### Dependency Metrics

Record active/idle database sessions, pool acquisition latency, cache hit ratio, broker reconnections, DNS lookups, and external API latency. These metrics help determine whether differences originate from the application or dependencies.

## 13. Preventing Instrumentation from Altering Measurements

Metrics, tracing, profilers, and logging incur overhead. They remain necessary to explain results, but must be applied consistently.

Rules:

- Use the same exporter, sampling rate, and log level across all groups.
- Synchronize scrape intervals and metric labels.
- Avoid debug logging during official measurement windows.
- Run profilers in separate trials if the profiler introduces significant overhead.
- Measure the baseline with instrumentation enabled at the exact production configuration.
- If comparing with and without instrumentation, treat those as two separate experiments.

Do not turn off metrics only on CRaC to reduce overhead while keeping metrics on cold start. If instrumentation has a substantial impact, measure its cost separately and report the actual production configuration.

## 14. Standardizing the Pre-Trial Procedure

A runbook ensures every trial starts from a comparable state. Example:

```text
Before trial
  1. Confirm the node/VM belongs to the correct hardware pool.
  2. Confirm image, checkpoint, and application digest.
  3. Check CPU/memory limits and ensure no abnormal background workload.
  4. Reset or standardize database/cache/fixtures per protocol.
  5. Confirm the load generator is idle and the script/version is correct.
  6. Confirm network and dependency health.

During trial
  1. Record t0 and startup/restore milestones.
  2. Wait for readiness under the same condition.
  3. Measure the first request if this is experiment B.
  4. Run the same warm-up/load phase if this is experiment C.
  5. Collect metrics within the fixed window.
  6. Record errors, dropped iterations, and environmental events.

After trial
  1. Save raw output and metadata.
  2. Clean up fixtures or reset dependencies.
  3. Check that the node did not suffer abnormal throttling/OOM.
  4. Mark the trial valid or exclude it according to predefined rules.
```

If multiple trials must run back-to-back on the same host, include a cool-down interval or thermal/CPU stabilization condition. Do not use arbitrarily different rest periods between the two groups.

## 15. Benchmark Manifest for Reproducibility

Save the benchmark configuration alongside results. A manifest enables others to rerun tests and understand why two measurements differ.

YAML Example:

```yaml
benchmark:
  name: orders-crac-comparison
  version: 3
  runId: run-2026-11-13-001
  experiment: steady-state
  randomSeed: 74129

application:
  buildId: orders-2.1.0-build1842
  artifactDigest: sha256:REPLACE_WITH_REAL_DIGEST
  checkpointId: orders-2.1.0-crac-1842
  jdkBuild: crac-jdk-build-pinned
  jvmOptionsProfile: production-g1-2g

environment:
  architecture: amd64
  nodePool: benchmark-cpu-pool
  cpuLimit: "4"
  memoryLimit: 8Gi
  kernel: recorded-kernel-version
  storageClass: local-nvme
  imagePullPolicy: IfNotPresent

workload:
  script: k6-orders-v3.js
  model: open-loop
  arrivalRatePerSecond: 200
  duration: 5m
  requestMix: orders-mix-v5
  datasetRevision: fixture-2026-11-10
  cachePolicy: warm-application-cache

measurement:
  startupTrials: 10
  steadyStateTrials: 10
  warmupDuration: 2m
  measurementDuration: 5m
  readinessDefinition: readiness-probe-success
```

Values in the manifest are illustrative only. Actual digests, kernel, CPU, storage class, and configuration must be gathered from the test environment. Do not put tokens, passwords, private keys, or user data into the manifest.

## 16. Example Design of a Cold Start vs. CRaC Comparison Campaign

Suppose the objective is to evaluate a REST service on the same node pool. Four experiments can be designed:

| Experiment | Cold start | CRaC restore | Primary Metrics |
|---|---|---|---|
| Startup | Start from the same JAR/runtime | Restore from a checkpoint of the same build | Process-to-ready and deploy-to-ready |
| First request | Send requests immediately after ready | Send requests immediately after ready | Latency of requests 1, 5, 10, 50, 100 |
| Steady-state | Same warm-up phase then fixed load | Same warm-up phase then fixed load | Throughput, p95/p99, CPU, memory, GC |
| Scale-out | Start 10 replicas in a batch | Restore 10 replicas in a batch | Batch time-to-ready, connection burst, storage/network load |

Each experiment runs multiple trials, with cold/CRaC order randomized or paired. Use the same dataset, request mix, load generator, and dependency state. Record whether image pull or checkpoint copy is included in deploy-to-ready.

### Example Results Table

The following numbers only illustrate presentation format, not actual results:

| Metric | Cold start | CRaC restore | Change |
|---|---:|---:|---:|
| Process-to-ready median | 8.2 s | 2.1 s | -74.4% |
| First request p95 | 420 ms | 95 ms | -77.4% |
| Steady-state throughput | 1,950 req/s | 1,940 req/s | -0.5% |
| Steady-state p95 | 82 ms | 83 ms | +1.2% |
| RSS after ready | 620 MiB | 710 MiB | +14.5% |
| Restore-to-ready p95 | — | 2.8 s | — |

Interpretation must be based on multiple trials and confidence intervals. If steady-state throughput is nearly the same while RSS increases, CRaC may help startup/first request at the cost of a larger memory footprint. If deploy-to-ready does not improve because image pull/checkpoint copy dominates total time, optimize artifact distribution or node caching.

## 17. Analyzing Results and Presenting Conclusions

A benchmark report should include:

1. Questions and hypotheses.
2. Description of the cold-start and CRaC configurations.
3. Hardware/runtime/environment manifest.
4. Workload model, request mix, offered load, and dataset.
5. Definitions of each timestamp/metric.
6. Trial count, execution order, seed, and trial exclusion rules.
7. Per-trial results and aggregate statistics.
8. Confidence intervals/variance and environmental events.
9. Limitations of the measurement and scope of generalization.

Avoid concluding "CRaC is X% faster" when only one route, one node, or one trial was measured. State explicitly: "Under workload X, on node pool Y, with JDK build Z and cache policy W, median process-to-ready decreased by ... across N trials; steady-state p95 ...". This phrasing specifies under which conditions the results apply.

### Reporting Variance as Well

Example per-trial table:

| Trial | Cold start ready | CRaC ready | Notes |
|---:|---:|---:|---|
| 1 | 8.0 s | 2.0 s | Valid |
| 2 | 8.4 s | 2.2 s | Valid |
| 3 | 8.1 s | 2.1 s | Valid |
| 4 | 10.7 s | 2.3 s | Cold experienced CPU throttling; handled per predefined rule |
| 5 | 8.3 s | 2.0 s | Valid |

If trial 4 is excluded, clearly state the reason and report results both with and without that trial if it affects the conclusion. Do not delete a trial simply because it reduces the observed improvement.

## 18. Common Mistakes

### Comparing Two Different Builds

One group may contain newer code/dependencies, preventing results from isolating the impact of CRaC. Use the same artifact digest and runtime, or document differences as a separate variable.

### Measuring Once and Concluding

A single run can be affected by CPU frequency, GC, or dependency jitter. Repeat and report the distribution across trials.

### Using Only the Same Request Count

Different request mixes or payloads yield different workloads. Lock route distribution, data shape, cache policy, and offered load.

### Using Only Fixed VUs to Conclude About Tail Latency

Closed-loop can lower offered load when the server slows down and hide queueing. Use open-loop when a fixed arrival rate is needed and monitor dropped iterations.

### Running the Load Generator on the Same Machine

The generator competes with the server for CPU/network and destabilizes results. Isolate the generator and monitor its capacity.

### Measuring Startup While Omitting Image Pull or Volume Mount

Process-to-ready may look good while deploy-to-ready remains slow. Report phases and clock scopes separately.

### Measuring Steady State to Conclude About the First Request

The warm-up phase erases initial differences. Measure first-request performance as a separate experiment.

### Failing to Standardize Cache and Dependencies

Database buffer cache, page cache, or external caches can give one group an advantage. Define the cache policy and reset/prime per protocol.

### Reporting Only Average Latency

Averages can hide tail latency and outliers. Report p50/p95/p99, sample count, error rate, and throughput.

### Excluding Outliers Without Rules

Excluding trials after inspecting results introduces bias. Define exclusion criteria in advance and preserve raw data.

### Changing Multiple Variables Simultaneously

Changing GC, heap, pool size, and node type simultaneously makes it impossible to tell which factor caused the difference. Vary only the defined variable in each experiment.

## 19. Pre-Publication Checklist

- [ ] Benchmark questions and hypotheses are clearly defined.
- [ ] Cold-start and CRaC use the same application build/digest.
- [ ] JDK, JVM options, container limits, and dependency versions are locked.
- [ ] Workloads share the same request mix, payload, dataset, and cache policy.
- [ ] Offered load or concurrency model is identical.
- [ ] The load generator runs independently and is not saturated.
- [ ] Startup, first-request, and steady-state are measured separately.
- [ ] Image pull, volume mount/copy, and dependency reconnection are reported separately or accounted for consistently.
- [ ] CPU, memory, disk, network, kernel, and storage are controlled/recorded.
- [ ] Logging, metrics, tracing, and profiling are identical across groups.
- [ ] Multiple trials are run and the order is randomized/paired.
- [ ] Sample size is sufficient for percentiles and the target effect size.
- [ ] Raw data, manifest, seed, and script version are saved.
- [ ] Outliers are handled per predefined rules and annotated.
- [ ] Conclusions state conditions, limitations, and variance clearly.

## 20. Conclusion

Reliable CRaC benchmarking must compare cold start and restore under identical workload, offered load, runtime, resources, and dependency state. Measure time from process/deploy to readiness, first-request latency, and steady-state performance separately. Use the same request mix, payload, dataset, cache policy, and load generator; choose open-loop or closed-loop according to the question being answered.

Repeat multiple trials, randomize order, pair when possible, and report medians, percentiles, variance, and confidence intervals. Control CPU, memory, disk, page cache, network, kernel, JDK, container limits, and instrumentation. Save the manifest alongside raw results so others can reproduce them. When presenting results, state benchmark conditions and scope of applicability clearly rather than deriving a generic improvement percentage from a single run. In doing so, decisions to adopt CRaC rest on observable and repeatable effectiveness under near-production conditions.

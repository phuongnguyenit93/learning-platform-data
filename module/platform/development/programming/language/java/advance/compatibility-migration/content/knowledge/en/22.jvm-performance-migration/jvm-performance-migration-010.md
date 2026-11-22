# Measuring Latency, Throughput, and Resource Usage Under Equivalent Load

In **Java Advance Compatibility Migration**, upgrading the JDK can alter performance even when business functionality remains correct. An application running on a newer JDK may reduce GC time yet increase CPU consumption, improve throughput at moderate load yet worsen p99 latency at high load, or reduce heap usage while total container memory rises due to thread stacks, code cache, and native allocations. Therefore, the fact that an application boots and functional tests pass is insufficient to declare a migration acceptable.

This lesson, **Measuring Latency, Throughput, and Resource Usage Under Equivalent Load**, belongs to the **JVM and Performance** chapter and walks through designing a trustworthy comparison between a **baseline** (current JDK/runtime) and a **candidate** (target JDK/runtime). The focus is ensuring both sides receive identical request types, arrival rates, data distributions, resource conditions, and measurement methodology, and then evaluating latency distributions, successful throughput, CPU, memory, GC, errors, and long-running stability.

You cannot declare one JDK faster merely from a headline number like "15% improvement". A technically valid statement must specify the workload, load level, SLOs, JVM flags, resource limits, repetition count, and variability. The ultimate goal is a **reviewable engineering decision**: proceed with rollout, tune configuration, investigate regressions, or roll back.

## 1. Identify the performance questions that need answers

Before picking a benchmark tool, articulate the exact questions:

- Given the same traffic and request mix, do users experience faster or slower responses?
- How many **successful business transactions** per second does the new release process?
- At what load level do p95/p99 latency or error rates breach SLOs?
- Does CPU consumption per successful request change?
- Do heap usage, RSS, native memory, thread count, or GC pressure increase?
- What do startup time, warm-up, long-running soak behavior, and headroom look like?
- Do observed differences stem from the JDK, GC defaults, frameworks, the database, or the test environment?
- In a rolling deployment, does a production canary actually serve the same workload as the baseline?

Measurements typically span multiple levels:

| Level | Goal | Common metrics |
|---|---|---|
| Microbenchmark | Compare an algorithm or Java API | ns/op, ops/s, B/op |
| Component benchmark | Compare a single module or adapter | operations/s, latency, allocations |
| Service benchmark | Compare a complete JVM service | p50/p95/p99, success RPS, CPU, RSS, GC |
| End-to-end benchmark | Compare user experience across network and dependencies | E2E latency, errors, retries |
| Capacity test | Find limits within SLO budgets | Max sustainable throughput |
| Soak test | Surface leaks, drift, and long-term issues | RSS trend, heap-after-GC, latency trend |

**Never use a microbenchmark to replace a service test.** A change making string processing 20% faster may have near-zero impact if 95% of request time is spent waiting on database queries.

## 2. Defining latency and measurement boundaries

**Latency** is the duration an operation takes between two defined milestones. For an HTTP service, distinguish:

1. **Client-observed response time:** from the client sending a request until receiving the complete response per contract.
2. **Server request handling time:** time inside the app server, potentially excluding gateway queueing or network transit.
3. **Downstream latency:** time spent calling databases, brokers, or external HTTP APIs.
4. **Queueing time:** time requests wait for workers, connections, or executors.
5. **GC/safepoint pauses:** one factor capable of delaying many requests at once, yet not the entirety of response latency.

Both versions must share the **exact same measurement boundary**. Comparing baseline server-processing p99 against candidate end-to-end p99 is flawed by design.

### 2.1. Measure distributions instead of averages alone

| Metric | Interpretation |
|---|---|
| p50 | 50% of samples have latency at or below this value |
| p90 | 90% of samples are at or below this value |
| p95 | 95% of samples are at or below this value |
| p99 | 99% of samples are at or below this value |
| p99.9 | 99.9% of samples are at or below this value; requires large sample sizes |
| Mean | Arithmetic average, sensitive to extreme outliers |
| Max | Highest observed latency in the measurement window |
| Timeouts | Requests failing to finish before the deadline |

Purely hypothetical example:

~~~text
A: mean=70 ms, p50=45 ms, p95=160 ms, p99=400 ms
B: mean=65 ms, p50=40 ms, p95=150 ms, p99=900 ms
~~~

If the SLO requires p99 below 500 ms, candidate B suffers a **severe tail regression**, despite better mean and p50 values.

### 2.2. Never drop timeouts from evaluation

Timed-out requests may lack a complete latency sample in a success-only histogram. If the candidate suffers more timeouts while reports include only successful requests, p99 can even look artificially better.

Always report all of:
- Latency distributions broken out by success/error or per policy.
- Request count, error count, and timeout count.
- Deadline/timeout threshold.
- Retries, rejected requests, or dropped operations.
- Success rate computed over **logical requests**, not HTTP attempts alone.

## 3. Throughput is completed operations

**Throughput** is commonly measured in requests/second, transactions/second, messages/second, or MB/s. Distinguish these quantities:

| Metric | Meaning |
|---|---|
| Offered load | Intended rate at which requests are scheduled |
| Actual arrivals | Rate at which requests are actually sent/received |
| Completed throughput | Rate at which operations finish |
| Successful throughput | Rate at which operations complete validly |
| Failed/rejected throughput | Rate returning errors or rejections |
| Dropped arrivals | Scheduled requests skipped because the load generator fell behind |

For example, a load generator configured for **400 arrivals/s** might only manage to send 370, with the server completing 350 successfully. You cannot report "400 RPS throughput" simply because the script set `rate=400`.

### 3.1. Tie throughput to business outcomes

In a payments API, useful throughput might be the rate of **payment intents processed exactly once**, rather than HTTP attempts. One logical request might trigger 3 attempts due to retries. Measuring attempts/s alone makes a retry-heavy system appear busier without producing higher business output.

For messaging, distinguish:
- Messages consumed/s.
- Unique events processed/s.
- Business state transitions/s.
- Redeliveries, duplicates, and DLQ counts.
- Consumer lag and backlog growth.

## 4. Resource usage: look beyond CPU or heap alone

During migration, resource efficiency should be evaluated alongside throughput and latency.

| Category | Metrics | What to watch |
|---|---|---|
| CPU | Core-seconds, utilization, throttling | Actual cores consumed vs. cgroup quotas |
| Heap | Used/committed/max, after-GC live set | Allocation churn and GC activity |
| Non-heap | Metaspace, code cache | Class loading and JIT compilation |
| Native | Thread stacks, direct buffers, JNI allocations | RSS can grow even as heap shrinks |
| GC | Count, pause duration, total pause, allocation rate | Throughput vs. pause trade-offs |
| Threads | Live/runnable/blocked counts, executor queues | Contention and starvation |
| Disk | IOPS, read/write bytes, fsync/latency | Logs, DB storage, and spill |
| Network | Bytes/s, connection counts, retransmits | HTTP/2, TLS, downstream traffic |
| Container | Working set, memory limits, OOM kills | Real resource budgets |
| Dependencies | DB/broker latency, pool saturation | Bottlenecks may sit outside the JVM |

**Heap used is not RSS.** An application with 700 MiB of heap used can still consume 1.8 GiB RSS due to metaspace, code cache, direct memory, and native allocations.

### 4.1. CPU-seconds per successful request

One metric for CPU efficiency:

\[
\text{CPU seconds per successful request}
=
\frac{\text{CPU core-seconds consumed}}{\text{successful requests}}
\]

Example on the same workload over a 60-second window:

~~~text
A: 1.2 CPU cores * 60s / 12,000 success = 0.006 CPU-s/request
B: 1.0 CPU cores * 60s / 12,000 success = 0.005 CPU-s/request
~~~

B consumes less CPU per unit output, **provided request mix, success rates, and data truly match**. Even then, this metric alone does not guarantee better p99 or memory budgets.

## 5. What does "equivalent load" mean?

Two test runs receive equivalent load when all primary drivers of processing cost are held constant or explicitly controlled with documented justification.

| Factor | Should stay equivalent | Why |
|---|---|---|
| Request mix | Endpoints, HTTP methods, read/write ratio | Operations vary in cost |
| Arrival pattern | Offered RPS, bursts, think time | Drives queueing behavior |
| Concurrency | Connections, in-flight requests, client workers | Shifts bottlenecks |
| Payload | JSON size, nesting depth, schema | Drives serialization cost |
| Dataset | Row counts, cardinality, indexes | Drives query cost |
| Data access | Hot/cold key skew | Determines cache hit ratios |
| Cache state | Cold/warm state, TTLs, eviction policy | Changes latency and CPU |
| Dependencies | DB, broker, downstream performance | I/O can dominate results |
| Resource limits | CPU, RAM, disk, network | Throttling and capacity ceilings |
| Replicas/routing | Instance count, placement, affinity | Load imbalance/skew |
| JVM options | Heap/GC flags per test goal | Mixing variables hides root causes |
| Tool settings | Versions, metric boundaries | Instrumentation bias |
| Warm-up/window | Duration and sampling window | Non-uniform JIT/GC state |

**Equivalence does not require every parameter to be identical in every experiment.** If the goal is comparing **default configuration as shipped**, each JDK uses its own default ergonomics, and the report must explicitly state two overall defaults are being compared. If the goal is isolating JIT/runtime impacts, pin heap/GC settings and vary the JDK across supported combinations.

### 5.1. Sample workload specification

~~~yaml
benchmark:
  scenario: "orders-read-write"
  warmup: "10m"
  steady: "20m"
  offeredRate: "300 requests_per_second"
  requestMix:
    getOrder: 0.65
    listOrders: 0.20
    createOrder: 0.10
    cancelOrder: 0.05
  data:
    orders: 1000000
    customers: 100000
    distribution: "privacy-safe-production-like"
    seed: 20261112
  constraints:
    errorsMaxPercent: 0.5
    p99MaxMilliseconds: 800
~~~

This is an **illustrative workload spec**, not a schema directly readable by every load tool. Translate it into configs/fixtures tailored for k6, Gatling, JMeter, or your internal tool.

### 5.2. Datasets and caches exert massive influence

At the same 300 RPS:
- Run A reads only 1,000 hot cached order IDs.
- Run B reads 1 million random IDs from the database.

The test no longer measures JDK differences alone. Standardize record cardinality, sizes, key distribution, cache warming, DB state, transaction side effects, and operation order.

For write benchmarks, reset or restore datasets between runs; otherwise growing tables and indexes gradually slow down subsequent runs.

## 6. Open-loop, closed-loop, and coordinated omission

### 6.1. Closed-loop load

In a closed-loop model, a virtual user sends the next request only after the previous request completes:

~~~text
Send -> Wait -> Receive -> Think -> Send next
~~~

When the server slows down, client send rates drop automatically. This fits tests modeling fixed active users with stable think times, yet it **masks slowdowns when real-world external arrival rates keep arriving steadily**.

### 6.2. Open-loop load

In an open-loop model, requests are scheduled according to an arrival rate largely independent of prior responses:

~~~text
t=0 ms     request 1
t=5 ms     request 2
t=10 ms    request 3
t=15 ms    request 4
~~~

When the server slows down, in-flight requests and queues build up. This is typically the right model for comparing capacity under **identical offered RPS**.

However, if the load generator lacks enough VUs, CPU, sockets, or network bandwidth, it cannot keep up with the schedule. Monitor **actual sent rate, dropped/late arrivals, load-generator CPU, and client errors** instead of blindly trusting the configured rate.

### 6.3. Coordinated omission

**Coordinated omission** is a measurement artifact where operations that should have started while the server paused/slowed are omitted from latency distributions.

For example, if the server pauses for 3 seconds, a closed-loop client records only one slow request because it waits before sending more. Under a real 100 RPS external workload, hundreds of requests would have queued behind that stall.

Mitigate bias by:
- Choosing the arrival model matching production reality.
- Using load generators/histograms with well-understood coordinated-omission handling.
- Recording both offered and completed RPS.
- Monitoring queue lengths, in-flight counts, and dropped iterations.
- Never stripping timeouts from reports.

No open-loop setup fits every system unconditionally. **Choose the load model based on the business question**, not because it produces prettier graphs.

## 7. Baseline–candidate design and root-cause isolation

A straightforward experiment:

~~~text
        Baseline                   Candidate
        JDK old                    JDK new
           |                          |
      Same application commit and artifact when possible
           |                          |
      Same workload, dataset, topology, resource limits
           |                          |
      Same metrics boundary and measurement method
           |                          |
      Compare latency / throughput / resources / errors
~~~

When upgrading the JDK alongside Spring Boot, Hibernate, and Netty, the benchmark measures a **bundle migration**—gains or regressions cannot be attributed solely to the JDK.

Where combinations are supported, isolate arms cleanly:

| Arm | JDK | Framework/dependencies | Objective |
|---|---|---|---|
| A | Old | Old | Production baseline |
| B | New | Old | Isolated JDK impact |
| C | New | New | Full bundle migration |
| D | Old | New | Framework impact if supported |

Never run an **unsupported** combination merely to fill out the grid. If only A and C are valid, state clearly that isolated JDK impact could not be measured separately.

### 7.1. Run metadata must be reproducible

Example record with placeholders:

~~~text
runId: A-001
gitCommit: COMMIT_SHA
artifactSha256: ARTIFACT_HASH
jdkVendor: VENDOR
jdkVersion: MAJOR_PATCH_BUILD
frameworkVersion: VERSION
containerImageDigest: IMAGE_DIGEST
gc: GC_AND_OPTIONS
xmsXmx: HEAP_VALUES
containerCpu: CPU_LIMIT
containerMemory: MEMORY_LIMIT
instanceCount: 1
datasetSeed: SEED
loadToolVersion: TOOL_VERSION
loadScenario: orders-v1-300rps
warmup: 10m
measurement: 20m
~~~

Also record hostname/node type, OS/kernel version, test start/end times, and dashboard/log links when required by process. **Never mistake placeholder labels for real telemetry.**

## 8. Controlling CPU and physical/virtualized environments

JVM performance depends on CPU microarchitecture, core counts, SMT, NUMA topology, clock frequency, thermal/power policies, and noisy neighbors.

Inside containers, examine:
- CPU requests and limits.
- Cpuset/quotas and processor counts visible to the JVM.
- Container CPU throttling periods and throttled time.
- GC, compiler, and application thread counts.
- CPU frequency scaling/turbo and noisy neighbors.
- Pod placement and node instance types.

A container with a 2 vCPU quota is not equivalent to an uncapped process on a host with 2 dedicated physical cores. **Same nominal CPU count** does not guarantee identical effective compute capacity.

### 8.1. CPU throttling distorts p99

If an application experiences a short CPU burst (e.g., JIT or GC) and hits its container quota, request queues grow. A candidate might deliver better steady-state CPU efficiency yet show worse tail latency due to JIT/GC bursts inside a small container quota.

When analyzing results, inspect side by side:
- CPU core-seconds.
- Quota/limit settings.
- Throttled time.
- Runnable thread counts.
- Request queue depth and p99.

Do not blame a JDK for worse GC pauses solely from high p99 when CPU throttling is severe.

## 9. Controlling memory, heap, and native allocations

Variables to capture:
- Container memory limit and swap configuration.
- `-Xms`, `-Xmx`, or percentage-based JVM flags.
- Heap used, committed, and maximum.
- Process RSS / working set.
- Metaspace, code cache, and thread stacks.
- Direct ByteBuffers and off-heap caches.
- JNI/native allocations.
- Page cache and cgroup memory metrics.

For example, a baseline capped at 2 GiB max heap vs. a candidate choosing 3 GiB ergonomically inside a 4 GiB container yields different memory and GC dynamics. That difference is worth measuring under shipped defaults, yet it is not an "equal heap size" comparison.

### 9.1. Heap after GC and memory leaks

Heap used cycling up and down across GCs is normal. Watch closely when:
- After-GC live set climbs steadily under flat workload.
- Old-generation occupancy fails to return to prior troughs.
- RSS keeps growing over long runs while heap stays flat.
- Direct memory, native allocations, or thread counts climb monotonically.
- GC frequency or pause lengths degrade over time.
- Containers hit OOM kills.

Extended soak tests expose trends that 5-minute runs miss.

## 10. JVM flags and default ergonomics

Upgrading the JDK can change JIT optimizations, GC heuristics, container awareness, compiler thread counts, and runtime defaults. Two distinct experiment modes exist:

**Equalized settings:** pin identical collectors, heaps, CPU/RAM limits, and supporting flags on both JDKs to minimize variables.

**Defaults as shipped:** let each JDK apply its own defaults while keeping container limits and workload identical, mirroring un-tuned real deployments.

Both views provide valuable insight, **never blend both into one muddy conclusion**. If the candidate JDK changes default GC collectors or drops old flags, explicitly record those constraints and rationales.

### 10.1. Inspecting JVM versions and flags

On supporting runtimes:

~~~bash
java -version
java -XX:+PrintFlagsFinal -version
~~~

Against a live process when authorized:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

Minimal runtime images may omit `jcmd`, or security policies may restrict it. Never broaden production privileges solely to collect benchmark data when safer capture paths exist.

## 11. Startup, warm-up, and steady state

JVMs need time to:
- Load and initialize classes.
- Wire dependency injection and application contexts.
- Complete JIT compilation and profile-guided optimization.
- Warm database connection pools, caches, and thread pools.
- Stabilize through initial GC cycles.

Never capture the first 10 seconds and call it steady-state throughput. Conversely, never **exclude startup from evaluation** when startup latency sits in your SLO (autoscaling, serverless, short-lived workers).

### 11.1. Segmenting test phases

| Phase | Evaluation focus | Key metrics |
|---|---|---|
| Cold start | Boot until ready | Startup time, peak CPU/RSS |
| Warm-up | JVM, caches, and pools stabilizing | JIT activity, cache hit rate, latency trend |
| Steady state | Sustained throughput under flat load | p50/p95/p99, RPS, CPU/request |
| Burst | Sudden load spike | Queue depth, errors, recovery time |
| Soak | Extended duration | Memory drift, GC, FDs, threads |

A 10-minute warm-up window is an **example**, not a universal rule. Confirm steady state using latency stabilization, compiler activity, cache hit rates, and resource curves.

## 12. Measuring load curves and saturation points

One service release can outperform at 100 RPS yet degrade at 500 RPS. Measure across a stepped load curve:

~~~text
50 -> 100 -> 200 -> 300 -> 400 -> 500 RPS
~~~

At each step:
- Keep workload mix and key distributions constant.
- Apply consistent warm-up and measurement windows.
- Capture offered, actual, and successful RPS.
- Capture latency percentiles, errors, and timeouts.
- Capture CPU, RSS, GC, queues, and downstream metrics.
- Confirm the load generator itself never saturates.

The **knee point** marks where the system saturates: increasing offered load yields minimal successful-throughput gain while latency, queueing, and errors climb sharply.

### 12.1. SLO-constrained capacity

Hypothetical acceptance criteria:
- p99 below 800 ms.
- Error/timeout rate at most 0.5%.
- No unbounded queue growth.
- Within container memory budgets.
- No severe CPU throttling.

Usable capacity is the **highest sustainable load still meeting all SLO and resource limits**, not peak RPS where most requests time out.

## 13. Constant-arrival-rate k6 load script example

Illustrative script targeting a read endpoint with k6:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    orderReads: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '10m',
      preAllocatedVUs: 80,
      maxVUs: 400,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.005'],
    http_req_duration: ['p(95)<300', 'p(99)<800'],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const base = __ENV.BASE_URL || 'http://127.0.0.1:8080';
  const orderId = 1 + Math.floor(Math.random() * 100000);
  const response = http.get(base + '/orders/' + orderId);

  check(response, {
    'expected status': (r) => r.status === 200,
  });
}
~~~

This is an **illustrative script**; adapt endpoints, authentication, datasets/fixtures, and thresholds for your real system. If some order IDs do not exist, `404` may represent valid business behavior rather than a performance failure; keep test datasets and expected statuses consistent.

`rate: 200` is merely the **offered arrival rate**. Always examine actual sent requests, successful completions, dropped iterations, errors/timeouts, VU saturation, and load-generator CPU/network usage.

### 13.1. Write workloads and idempotency

Never load-test real production payment, email, or fulfillment flows. For create/update benchmarks:
- Prepare isolated, PII-free test datasets.
- Handle idempotency and unique business keys cleanly.
- Reset or reconcile the DB between test runs.
- Prevent sending real emails, SMS, or payments.
- Verify rollback, retry, and transaction states.
- Measure dataset growth, index bloat, and write amplification.

A benchmark that corrupts state or triggers real external side effects is unacceptable.

## 14. Percentiles and statistical aggregation pitfalls

### 14.1. Never average p99 values

The p99 across 60 one-minute windows does **not** equal the arithmetic mean of those 60 per-minute p99s. Percentiles reflect underlying distributions and do not combine linearly.

To aggregate properly:
- Merge raw latency samples, or
- Merge compatible histograms / quantile sketches supported by your tooling.
- Document bucket resolution and approximation precision.
- Never pass `avg(p99)` off as global p99.

### 14.2. Ensure sufficient sample sizes

p99 captures the slowest 1% tail. With only 100 requests, a single outlier shifts p99 wildly, making results noisy. p99.9 needs far larger sample counts. Always report sample counts, run durations, timeout rules, and repetition counts.

A 3 ms shift is meaningless if run-to-run noise swings ±20 ms. Avoid treating every slight fluctuation on a chart as a real regression.

### 14.3. Grouping metrics by cohort

Slice metrics by:
- Endpoint or operation name.
- HTTP status / error class.
- Payload size cohort.
- Runtime/JDK version.
- Instance or node group.
- Cache hit/miss or DB query class.

Never put raw user IDs or order IDs into metric labels due to high cardinality costs and privacy risks.

## 15. GC: measure pause times and CPU cost, not collection count alone

GC behavior can change when changing the JDK, collector, or heap size. Collect:
- GC counts, pause counts, and total pause time.
- Pause duration distributions when sample counts suffice.
- Allocation rate and bytes allocated per request.
- Heap occupancy before and after GC.
- Promotion rate / old-generation pressure.
- Concurrent GC CPU usage.
- Safepoint durations and thread states.

### 15.1. GC pauses are only part of request latency

A 100 ms GC pause can delay many concurrent requests together. Still, a 2-second p99 might actually stem from a 1.9-second database lock, connection-pool queueing, or CPU throttling. Correlate request traces with GC/JFR timelines; **never infer causation merely because two charts rose together**.

### 15.2. GC logging

HotSpot Unified Logging example:

~~~bash
java \
  -Xms2g -Xmx2g \
  -Xlog:gc*,safepoint:file=/var/log/orders/gc.log:time,uptime,level,tags:filecount=5,filesize=20m \
  -jar orders.jar
~~~

Ensure the log directory exists with write permissions. Log formats and tags vary by JDK and collector. Logging also carries slight I/O overhead; apply matching instrumentation to both runs or isolate logging overhead separately.

### 15.3. Collector trade-offs

Collectors prioritizing tail latency can burn extra CPU or RAM; throughput-focused collectors can tolerate longer pauses. No collector dominates everywhere. When moving from G1 to ZGC or changing configs, report the delta as **JDK + GC configuration** rather than blaming the Java compiler/JIT for every shift.

## 16. Memory leaks, RSS, and native memory

JVM process memory spans several components:

~~~text
Process RSS / memory
   |
   +-- Java heap
   +-- Metaspace and class metadata
   +-- JIT code cache
   +-- Thread stacks
   +-- Direct buffers / off-heap caches
   +-- JNI and native libraries
   +-- Memory mappings / runtime structures
~~~

During soak tests, watch:
- Does heap after GC stabilize?
- Does RSS climb even while heap stays flat?
- Do thread or file-descriptor counts climb endlessly?
- Does direct/native memory grow with network traffic?
- Does container memory approach the OOM ceiling?
- Do GC pauses lengthen steadily over time?

### 16.1. Native Memory Tracking

On supporting HotSpot JVMs, enable NMT at startup:

~~~bash
java -XX:NativeMemoryTracking=summary -jar orders.jar
~~~

Then inspect summaries when permitted by runtime and permissions:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT incurs overhead and does not track every non-JVM native allocation; understand its limits. Never benchmark an NMT-enabled candidate against an NMT-disabled baseline and blame the entire CPU delta on the JDK.

### 16.2. Heap dumps and sensitive data

Heap dumps cause long pauses, memory spikes, and capture tokens, PII, and secrets. Never take production heap dumps routinely as a metrics substitute without justification, approval, and secure retention rules. Start with lightweight counters, JFR, or NMT, capturing full dumps only when diagnosis requires it.

## 17. JFR and profiling

**Java Flight Recorder (JFR)** captures JVM events for investigating:
- CPU hotspots and execution sampling.
- Allocation rates and allocation stack traces.
- GC and safepoint activity.
- Lock contention, thread states, and thread parking.
- Class loading and JIT activity.
- Selected socket and file I/O events.

Example short recording where authorized:

~~~bash
jcmd <pid> JFR.start name=perf settings=profile duration=120s filename=/tmp/perf.jfr
jcmd <pid> JFR.check
~~~

Analyze recordings using JDK Mission Control or JFR analysis tools.

### 17.1. Controlling profiling overhead

JFR overhead is non-zero; event selections, sampling thresholds, and duration govern cost. Record the JDK version, event settings, thresholds, duration, and analysis approach. If performance deltas are small (a few percent), confirm conclusions on un-profiled runs.

### 17.2. Using profiling to test hypotheses

Examples:
- Higher CPU/request → inspect stack samples, JIT compilation, and inlining.
- Higher p99 → inspect GC pauses, lock contention, and thread parks.
- Higher RSS → inspect allocations, native memory, and thread counts.
- Lower throughput → inspect queueing and downstream waits.
- Slower cold start → inspect class loading and framework initialization.

Profiling highlights where time or allocations go, **without proving root cause by itself**. Re-run the exact workload benchmark after applying fixes to confirm gains.

## 18. JMH for controlled microbenchmarks

**Java Microbenchmark Harness (JMH)** fits testing performance hypotheses at the method/algorithm level. It manages warm-up iterations, measurement iterations, process forks, benchmark states, and blackholes to avoid typical microbenchmark traps.

Naive loops timing `System.nanoTime()` often fail due to:
- Dead-code elimination.
- Constant folding.
- Missing JIT warm-up.
- Skewed inlining or deoptimization.
- Mixed class-loading/GC noise.
- Harness overhead overshadowing the target method.

### 18.1. JMH example

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 10, time = 1)
@Fork(3)
public class MapLookupBenchmark {
    private Map<Integer, String> data;
    private int index;

    @Setup(Level.Trial)
    public void setup() {
        data = new HashMap<>();
        for (int i = 0; i < 10000; i++) {
            data.put(i, "value-" + i);
        }
    }

    @Benchmark
    public String lookup() {
        index = (index + 1) % 10000;
        return data.get(index);
    }
}
~~~

Running requires matching JMH dependencies and annotation processing/plugins for your build, compiler, and JDK. This demonstrates testing one isolated operation—**never extrapolate microbenchmarks directly to HTTP throughput**, where networking, serialization, databases, and queueing dominate.

## 19. Application metrics, tracing, and downstream behavior

A typical request path spans:

~~~text
Client -> Gateway -> Server queue -> Authentication
       -> Business work -> Database / HTTP downstream
       -> Serialization -> Response
~~~

When client-observed p99 rises, isolate:
- Ingress / load-balancer waiting.
- Executor or connection-pool queueing.
- CPU-bound application work.
- GC, JIT, or safepoint stalls.
- DB, query, or cache misses.
- Network/TLS and remote downstream calls.
- Response serialization.

Use distributed tracing and per-stage metrics to find slow segments. **Never sum segment p99s into an overall p99**: tail quantiles across distributions do not add linearly.

### 19.1. Little's Law

In a stable system:

\[
L = \lambda W
\]

Where:
- \(L\): average number of operations concurrently in the system.
- \(\lambda\): average steady-state throughput.
- \(W\): average time spent in the system.

For example, 200 requests/s with a 0.1 s mean response time implies roughly 20 in-flight requests under the chosen boundary. This equation does not predict p99 directly; if queues keep growing or requests drop, the steady-state assumption breaks down.

## 20. Repetition, run order, and variability

Running A once then B once invites bias from:
- CPU thermal/power throttling or frequency scaling.
- Cold vs. warm caches.
- Background OS tasks or database compaction.
- JIT compilation phases.
- Network jitter and noisy neighbors.
- Unaligned GC cycles or mutated datasets.

Alternate multiple A/B pairs in balanced order:

~~~text
A1 -> B1 -> B2 -> A2 -> A3 -> B3
~~~

Apply identical workload/dataset resets, warm-up windows, and measurement durations to every run.

### 20.1. Report variability, not single numbers

For p99, throughput, and CPU/request:
- Save individual run figures and sample sizes.
- Report median/min/max or cross-run dispersion.
- When computing confidence intervals, pick methods valid for autocorrelated time-series data; never treat every HTTP request inside one run as an independent sample.
- Distinguish statistical significance from business significance.

A 1% difference inside ±5% run-to-run noise proves nothing. Conversely, a persistent +25% p99 spike breaching SLOs is an immediate operational blocker without needing elaborate statistics.

## 21. Sample comparison table and interpretation

**Numbers below are hypothetical illustrations, not real benchmark data:**

| Metric at 300 offered RPS | Baseline A | Candidate B | Interpretation |
|---|---:|---:|---|
| Actual sent RPS | 300 | 300 | Equivalent load |
| Successful RPS | 298 | 299 | B slightly higher |
| Error + timeout | 0.7% | 0.3% | B shows better reliability |
| p50 latency | 55 ms | 50 ms | B faster |
| p95 latency | 160 ms | 145 ms | B faster |
| p99 latency | 420 ms | 510 ms | **B shows tail regression** |
| Avg CPU cores | 2.1 | 1.9 | B uses less CPU |
| CPU throttled time | 0 | 0 | Unmasked by quota throttling |
| Process RSS | 1.8 GiB | 2.0 GiB | B increases memory footprint |
| Heap after GC | 0.70 GiB | 0.65 GiB | B lowers live heap |
| Total GC pause/min | 0.8 s | 0.5 s | B lowers total pauses |
| DB p99 | 220 ms | 350 ms | Downstream needs investigation |

If the p99 SLO is 500 ms, candidate B **fails the gate** even though mean, median, CPU, and GC metrics improved. With a 1.9 GiB RSS budget, B also misses its memory footprint budget. That is why migration decisions must evaluate **multiple metrics and budgets together**.

### 21.1. Computing percentage change

\[
\Delta \% =
\frac{\text{candidate} - \text{baseline}}
{\text{baseline}}\times 100\%
\]

For instance, p99 shifting from 400 ms to 500 ms is +25%, which is **worse** when minimizing latency. Successful throughput rising +25% is typically **better** when error rates and SLOs stay clean. Never apply the same "positive delta = green" coloring rule to every metric.

## 22. Performance gates and rollout decisions

A performance gate needs both **absolute thresholds** and **regression limits**, for example:

~~~yaml
performanceGate:
  workload: "orders-steady-300rps"
  measuredWindow: "20m-after-10m-warmup"
  latency:
    p99MaxMs: 500
    p95RegressionMaxPercent: 10
  throughput:
    successfulMinRps: 295
  reliability:
    errorAndTimeoutMaxPercent: 0.5
  resources:
    cpuPerSuccessRegressionMaxPercent: 10
    rssMaxGiB: 2.2
  loadGenerator:
    requireDroppedIterationsZero: true
~~~

This policy is illustrative, not a default tool schema. Derive concrete thresholds from SLOs, error budgets, capacity planning, and cost constraints.

### 22.1. Absolute vs. relative gates

If baseline p99 was 900 ms and candidate achieves 850 ms, that is an **improvement**, yet still **fails** a 500 ms SLO. If baseline was 100 ms and candidate hits 110 ms, that is a 10% regression while both remain comfortably under budget; final acceptance depends on policy.

### 22.2. Tie gates to business-critical paths

Never gate solely on a popular GET endpoint if payment or checkout flows carry strict SLOs. Cover:
- Read-heavy scenarios.
- Write-heavy scenarios.
- Latency-critical paths.
- Burst/capacity scenarios.
- GC/allocation-heavy scenarios where relevant.
- Soak stability.

A release might boost read RPS while slowing write transactions or triggering duplicate writes under altered retry behavior.

## 23. Benchmarking on containers and Kubernetes

When running inside containers, record:
- Container image digests and JDK vendor/builds.
- CPU requests, limits, and throttling stats.
- Memory limits, RSS/working set, and OOM events.
- Replica counts, node instance types, and CPU architecture.
- HPA/VPA autoscaling policies if enabled.
- Ingress/load-balancer routing and session affinity.
- Database/broker capacity and connection-pool sizing.

If autoscaling adds extra replicas to the candidate while the baseline keeps fixed replicas, do not report that as improved **per-instance performance**. Split into two separate tests:
1. **Per-replica capacity** with fixed replica counts.
2. **System-level autoscaling behavior** under identical scaling policies.

### 23.1. A production canary is not automatically an equivalent benchmark

Canary pods may serve different tenants or sessions:
- Different request mix from baseline pods.
- Different data hotness and cache warmth.
- Different underlying node CPU models.
- Lower canary traffic keeping pods far from saturation.
- Varying load across shared downstream backends.

Canaries validate **operational safety on live traffic**, whereas isolating pure JVM performance impact often requires controlled traffic replay, paired instances, or matched cohort analysis.

## 24. Practice exercise: designing an experiment

**Hypothetical scenario:** An Orders service runs on JDK 17 and targets JDK 21. It exposes a read-heavy API plus write endpoints backed by PostgreSQL. Target SLO is GET p99 < 600 ms at 400 RPS, errors ≤ 0.5%, inside a 4 vCPU / 4 GiB RAM container.

### 24.1. A/B plan

1. Pin a single application commit/artifact and dependency graph if isolating the JDK.
2. Build two container images differing only in JDK vendor/version; record digests.
3. Pin or explicitly record GC, heap, and JVM flags on both sides.
4. Prepare a privacy-safe dataset of one million orders with fixed seed and key skew.
5. Keep DB config, indexes, and connection-pool settings equivalent.
6. Execute warm-up before starting measurement windows.
7. Sweep 200, 300, 400, and 500 RPS under the fixed request mix.
8. Capture successful RPS, p50/p95/p99, timeouts, and dropped arrivals.
9. Capture CPU, RSS, heap-after-GC, GC pauses, queues, and DB latency.
10. Repeat alternating A/B runs with dataset resets between write runs.
11. Run an extended soak test checking memory and resource drift.
12. If regressions surface, capture JFR/GC logs/profiles and re-verify after fixes.
13. Apply performance gates prior to canary/rollout sign-off.

### 24.2. Interpreting mixed results

Suppose the candidate cuts CPU by 8% yet p99 at 400 RPS climbs 30%. Causes may include:
- Changed GC/JIT behavior under higher load.
- CPU throttling or queueing stalls.
- Different default DB connection-pool behavior.
- Unbalanced request/key skew across runs.
- Load generator failing to sustain arrival rates.
- Unrecorded dependency/framework behavior shifts.

Never declare "the new JDK is slower" or "the new JDK is better" until checking test validity and pinpointing which layer changed.

### 24.3. Example bounded conclusion statement

A solid engineering report might state:

> Under the pinned Orders 400 RPS workload, container resource limits, and fixed dataset, the candidate improved CPU efficiency, yet p99 latency breached the performance gate threshold. Consequently, full rollout is held. Raw run metrics, workload specs, GC logs, and JFR profiles are archived for investigation.

This is a **reporting template example**, not a real finding about JDK 21 in general.

## 25. Common mistakes

- **Comparing p99 across different request mixes:** unequal workloads.
- **Looking only at sent RPS, ignoring completed RPS:** confusing offered load with throughput.
- **Omitting timeouts/errors from reports:** artificially beautifies latency.
- **Closed-loop hiding coordinated omission:** understates tail latency.
- **Load generator bottlenecks:** scripts fail to hit configured arrival rates.
- **Differing datasets, cardinality, or cache state:** ceases measuring runtime effects.
- **Using means instead of p99 for latency-sensitive APIs:** misses tail regressions.
- **Computing global p99 by averaging bucket p99s:** mathematically invalid.
- **Sampling right after boot as steady state:** skips JIT and cache warm-up.
- **Ignoring cold starts when autoscaling:** misses part of the SLO.
- **Equating heap used with process RSS:** different memory scopes.
- **Ignoring CPU quotas/throttling:** mismatched compute capacity.
- **Measuring only a single run:** skewed by CPU, cache, and GC timing noise.
- **Changing JDK, framework, GC, and DB driver together:** hides root cause.
- **Assuming every p99 spike comes from GC:** may be locks, queues, DB, or TLS.
- **Using JMH alone to predict HTTP service speed:** omits networking, I/O, and DBs.
- **Enabling JFR on one arm only:** asymmetrical measurement overhead.
- **Skipping dataset resets after write load:** later runs hit bloated tables/indexes.
- **Comparing skewed canary traffic to baseline:** introduces selection bias.
- **Scaling replica counts and claiming per-instance speedup:** non-equivalent test setups.
- **Discarding artifact/JDK/build metadata:** makes results irreproducible.
- **Failing to verify business correctness under load:** fast wrong answers still fail.

## 26. Checklist before approving performance migration

- [ ] Recorded JDK vendor, version/build, and image digests for baseline and candidate.
- [ ] Pinned source commit, artifact checksums, dependency versions, and JVM flags.
- [ ] Separated isolated JDK benchmarks from bundled framework upgrades where supported.
- [ ] Locked workload specs: request mix, arrival pattern, payloads, dataset, and seeds.
- [ ] Controlled cache state, DB/broker state, and downstream dependencies.
- [ ] Pinned/recorded CPU/RAM limits, node types, replica counts, and network topology.
- [ ] Confirmed load generators had ample headroom with zero unexpected dropped arrivals.
- [ ] Selected open-loop or closed-loop per business goals and addressed coordinated omission.
- [ ] Evaluated cold start, warm-up, steady state, burst, and soak phases as applicable.
- [ ] Measured at identical boundaries with enough samples for p50/p95/p99 and errors/timeouts.
- [ ] Reported actual arrivals, successful throughput, and retry attempts.
- [ ] Avoided aggregating global percentiles via averaged per-bucket percentiles.
- [ ] Captured CPU core-seconds, CPU throttling, and CPU per successful request.
- [ ] Captured heap, RSS, and non-heap/native memory usage.
- [ ] Tracked GC pause/counts, after-GC heap, and allocation rates.
- [ ] Cross-checked queues and DB/broker/network latencies to isolate bottlenecks.
- [ ] Repeated benchmarks across multiple balanced runs and reported variance.
- [ ] Enforced both absolute SLO gates and relative regression thresholds.
- [ ] Validated production target load and capacity headroom.
- [ ] Ran extended soak tests when leaks or RSS drift risks exist.
- [ ] Archived JFR/GC/profiling evidence for any investigated regressions.
- [ ] Verified business correctness and side effects under load.
- [ ] Archived run metadata, raw metrics/histograms, and canary/rollback decisions.

## 27. References

The following resources help implement tooling and verify semantics; check documentation matching your project's pinned versions:

- [OpenJDK JMH](https://github.com/openjdk/jmh): Java microbenchmarking, warm-up, forks, and benchmark states.
- [JDK jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): inspecting JVM flags, GC, and managing JFR.
- [JDK java Launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): JVM options and `-Xlog`.
- [Java Flight Recorder API](https://docs.oracle.com/en/java/javase/21/jfapi/): JFR events and recordings.
- [JDK Mission Control](https://openjdk.org/projects/jmc/): analyzing JFR recordings and profiling.
- [Grafana k6 Documentation](https://grafana.com/docs/k6/latest/): arrival-rate execution, metrics, thresholds, and dropped iterations.
- [HdrHistogram](https://github.com/HdrHistogram/HdrHistogram): latency histograms and coordinated omission handling.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/): JVM/application metrics and timers.

Docs labeled "latest" may differ from the release you actually run. For internal system performance reports, what matters most is **keeping workload profiles, metric definitions, run durations, raw samples/histograms, and environments reproducible**.

## 28. Conclusion

**Measuring performance when upgrading a JDK is a controlled comparison, not firing off a few requests and checking mean response time.** Latency must be measured at identical boundaries with full p95/p99 and timeout reporting; throughput must separate offered load from successful business completions; resource usage must cover CPU throttling, heap, RSS, GC, native memory, and downstream dependencies.

A reliable workflow is **freeze workload/dataset → pin runtime and resource limits → warm up → sweep load curves → capture latency/throughput/errors/resources → alternate repeated A/B runs → diagnose via JFR/GC/profiling → enforce SLO/capacity gates → execute canary/rollback with evidence**. When comparisons truly run under **equivalent load**, teams can distinguish genuine runtime improvements from caching artifacts, load-generator limits, GC defaults, or framework changes—making Java upgrade decisions on sound engineering and operational footing.

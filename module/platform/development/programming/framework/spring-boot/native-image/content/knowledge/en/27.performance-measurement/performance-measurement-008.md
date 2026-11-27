# Keeping Data, Configuration, Dependencies, and Infrastructure Identical When Comparing

## 1. Why Control Benchmark Conditions?

When evaluating Spring Boot on the JVM versus GraalVM Native Image, the goal is to measure the impact of the **runtime model** on the application: startup time, latency, throughput, CPU, and memory. Results are meaningful only when both versions perform the exact same work under equivalent conditions.

If the JVM build hits a closer database, has a warm cache, uses a larger pool, or runs on a host with more CPUs, observed differences cannot be attributed to JVM or Native Image. Likewise, if a native build drops dependencies, disables a listener, or uses smaller payloads, the benchmark is no longer comparing the same application.

This lesson belongs to the **Performance Measurement** chapter of the **SPRING_BOOT_NATIVE_IMAGE** module. The module practices compiling Spring Boot into GraalVM Native Image via Spring AOT to evaluate startup and memory gains; it also covers Maven/Gradle builds, configuring reflection and resources, compatibility testing, container packaging, and operating native builds. Here, we establish a fair, repeatable, and explainable measurement methodology.

After this lesson, learners will be able to:

- Identify variables that must remain constant when comparing JVM and Native Image.
- Standardize data, request mix, application configuration, and dependencies.
- Provision identical CPU, memory, network, and auxiliary service limits.
- Separate cold start from post-warm-up performance.
- Measure latency, throughput, CPU, and memory using meaningful metrics.
- Repeat benchmarks, aggregate data, and state the bounds of conclusions.

Overarching principle: **change only the factor under study**. In the primary comparison, that factor is how the application runs: JVM or Native Image. Every other factor must stay identical or be explicitly documented if exact parity is impossible.

## 2. Defining the Independent Variable and Controlled Conditions

Before running a benchmark, write out the exact question to answer. For example: "Under the same commit, same data, and a 2 CPU / 1 GiB container limit, does native reduce readiness time and RSS compared to JVM?"

In this experiment:

- **Independent variable:** the runtime being compared (JVM or Native Image).
- **Dependent variables:** startup-to-ready, latency, throughput, CPU, RSS, peak memory, and selected metrics.
- **Controlled variables:** source code, application dependencies, data, request mix, business configuration, allocated resources, infrastructure, and measurement tools.

The following table serves as a condition checklist:

| Group | Must Keep Identical | Examples to Record |
|---|---|---|
| Source | Same commit and same business changes | Git commit, build number |
| Spring/AOT | Same Spring Boot, Framework versions, and matching AOT config | Spring Boot, Java, Native Build Tools |
| Dependencies | Same runtime library and driver versions | Dependency lock/tree, artifact checksums |
| Data | Same snapshot, counts, distribution, and data state | Dataset ID, row count, seed |
| Requests | Same payload, endpoint ratios, concurrency/arrival rate | Load scenario, duration |
| Configuration | Same profile, feature flags, and business values | Config revision, environment variables |
| Infrastructure | Same CPU, memory, kernel, network, and external services | Host, architecture, cgroup limits |
| Measurement | Same load generator, metric definitions, and sampling | Tool/version, dashboard/queries |

Never use results from two runs lacking this condition record to declare one runtime faster. If a required condition differs, document the difference and treat it as a confounding factor to control in the next run.

## 3. Keeping Source, Versions, and Dependencies Identical

Start from the exact same commit. Build both the JVM artifact and native artifact from the same source tree, application configuration, and runtime dependency set. Spring AOT may generate extra initialization code and RuntimeHints; that is output supporting the native runtime, not a reason to alter business logic between builds.

Record at minimum:

- Git commit SHA and working tree status.
- Spring Boot, Spring Framework, and Java/JDK versions.
- GraalVM and Native Image Build Tools versions.
- Maven/Gradle wrapper version and build profile.
- Dependency tree or lockfile of the runtime classpath.
- Native build arguments, optimization level, GC, and PGO if any.
- Checksums of the JAR, native executable, and container image.

Example commands to capture build info:

```bash
git rev-parse HEAD
./mvnw -version
java -version
native-image --version
./mvnw -Pnative dependency:tree
```

With Gradle, you can use:

```bash
git rev-parse HEAD
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
```

`dependency:tree` or Gradle reports catch dependency mismatches; they do not replace inspecting final artifacts. Confirm that required runtime libraries, JDBC drivers, messaging clients, serializers, and native libraries share the exact same versions across both builds.

Native Image requires the GraalVM compiler and certain build-time dependencies. Those build tools do not have to appear in the JVM runtime package. What must stay equivalent are the **dependencies the application actually executes when handling the workload**. Document the build toolchain separately so others can reproduce artifacts.

Do not strip dependencies or features only in the native profile to shrink the binary and then compare it against a full JAR. If a product uses a trimmed deployment profile, apply an equivalent profile to both runtimes and verify identical functionality.

## 4. Keeping Data and Initial State Identical

Data heavily dictates query, serialization, cache, allocation, and network costs. The exact same SQL query can be instant on 100 rows yet much slower on millions of rows or skewed distributions.

Prepare a reproducible dataset:

- Same record counts and table relationships.
- Same string lengths, JSON sizes, collection sizes, and null ratios.
- Same hot-key/cold-key distribution and cardinality.
- Same indexes, schema, statistics, and database version.
- Same cache state at the start of every run.
- Same random seed if the benchmark generates random data/requests.

For write workloads, do not let the first run mutate state in a way that helps or hurts the next run. You can restore a database snapshot before each run, use separate namespaces with identical seed data, or run read-only workloads if that matches the research question. When resets are impossible, design records and request sequences so both runs observe the same starting state.

Caches must be explicitly defined. There are two distinct questions:

- **Cold-cache:** the application starts with empty caches, or database/proxy caches have been reset.
- **Warm-cache:** caches have been warmed with an identical request sequence before measurement begins.

Never compare a warm-cache JVM run against a cold-cache native run. If both cases matter, run two separate benchmarks and document how caches were reset or warmed.

Use the same database, broker, object storage, and auxiliary services. When write workloads prevent sharing one instance, provision two equivalent environments from the same snapshot, configuration, and network placement. Do not let one runtime reach its database over an internal network while the other hits a co-located database on the same host.

## 5. Keeping Application Configuration and Behavior Identical

Identical source does not guarantee two processes run identical configurations. Profiles, feature flags, environment variables, cron jobs, connection pools, or cache sizes can alter execution paths.

Create a canonical configuration and supply it to both runtimes. Areas to reconcile include:

| Area | Examples |
|---|---|
| Spring profile | `spring.profiles.active` |
| HTTP | port, compression, TLS, server thread pool |
| Database | URL, pool size, timeout, transaction isolation |
| Cache | provider, max entries, TTL, eviction policy |
| Messaging | broker, topic/queue, consumer group, concurrency |
| Serialization | ObjectMapper modules, naming strategy, schema version |
| Scheduling | task enablement, cron, timezone, initial delay |
| Logging/metrics | log level, appenders, exporter, sampling |
| Feature flags | enable/disable identical features and business branches |

Some runtime options exist on only one platform. For instance, JVM has `-Xms`, `-Xmx`, GC choices, and JIT flags; Native Image has heap/GC options and build-time optimizations. You cannot force two runtimes to take identical flags lacking shared semantics. Instead, maintain **identical resource limits and application behavior**, while explicitly documenting runtime-specific options.

Consider running two passes:

1. **Baseline:** use each runtime's defaults or current production settings, matching only CPU/memory limits. Record all runtime options.
2. **Tuned:** tune JVM and Native Image individually toward equivalent targets, then re-measure. Record configurations, tuning effort, and results.

Do not compare an untuned JVM against a heavily tuned native image and credit the entire gap to the runtime model. Also avoid changing pool sizes, caches, or feature flags on only one side during a baseline pass.

Before measuring, run a functional test suite confirming both builds produce identical outputs for identical inputs: status codes, response bodies, database side effects, emitted messages, and business errors. A benchmark without functional parity is not a valid comparison.

## 6. Keeping Infrastructure and Resource Limits Identical

Run both versions on the same machine type or equivalently configured hosts. Record CPU model/core count, RAM, architecture, kernel, filesystem, container runtime, and background load state. Avoid running benchmarks concurrently on the same host if they contend for CPU, memory bandwidth, disk, or network.

When benchmarking in containers, assign identical CPU quotas and memory limits. Example:

```bash
docker run --rm \
  --cpus=2 \
  --memory=1g \
  --memory-swap=1g \
  -p 8080:8080 \
  my-service:jvm
```

Run the native build with identical limits:

```bash
docker run --rm \
  --cpus=2 \
  --memory=1g \
  --memory-swap=1g \
  -p 8080:8080 \
  my-service:native
```

2 CPUs and 1 GiB are illustrative only; pick limits reflecting your actual workload. In Docker, `--cpus` caps CPU available to the container, while `--memory` sets the memory limit. `--memory-swap` governs combined memory and swap allowance, so keep it identical as well. If you set only memory limit without controlling swap, two runs may behave differently under memory pressure.

Keep these additional factors equivalent:

- CPU affinity/cpuset if processes are pinned to cores.
- Network namespace, DNS, TLS, connection reuse, and distance to external services.
- Filesystem and mount options, especially when workloads read/write files.
- Replica count and resource contention level.
- User permissions, file descriptor limits, and process/thread limits.

JVM and native container images may differ in base image because binaries need different runtime libraries. Use the same OS family, architecture, and libc compatibility where possible; if they differ, document image size, runtime libraries, and potential impact. Distinguish **runtime benchmarks under identical container limits** from **image size benchmarks**: they answer different questions.

## 7. Choosing a Representative Workload and Identical Load Model

A benchmark is valuable only if the workload resembles real work the application performs. Do not use a static-string endpoint to conclude that an entire Spring Boot application is faster.

Define request mix based on real traffic, for example:

| Workload Group | Illustrative Share | What to Hold Constant |
|---|---:|---|
| Data read | 60% | Same queries, row counts, cache state |
| Data write | 20% | Same transactions, record sizes, and reset strategy |
| Serialization/report | 15% | Same payload sizes, format, and schema |
| Health/metadata | 5% | Same endpoints and frequency |

Percentages above are illustrative. Derive shares from production telemetry or defined use cases, scrub sensitive details, and synthesize payloads using test data.

Keep the load generation model identical:

- **Concurrency:** number of concurrent requests or virtual users.
- **Arrival rate:** new requests per second; useful when holding offered load constant.
- **Duration:** warm-up duration and measurement duration.
- **Payload mix:** ratio of small/large requests and endpoints.
- **Connection behavior:** keep-alive, TLS, HTTP version, and connection count.
- **Think time/retry:** wait times, retry policies, and timeouts.

Fixed concurrency and fixed arrival rate answer different questions. Under fixed concurrency, completed request rate drops as latency rises. Under fixed arrival rate, the system must process requests arriving at a scheduled pace; when overloaded, queues and latency grow. Pick the model matching your goal and keep it identical across runtimes.

Run the load generator on a separate host or confirm it has ample spare CPU so it never becomes the bottleneck. The exact same script, tool version, and parameters must drive both versions. When replaying data, preserve ordering or use the same seed to produce identical request sequences.

## 8. Separating Cold Start, Warm-Up, and Steady-State

Do not lump every result into one measurement. JVM and Native Image have different startup and runtime optimization models, so measure stages separately:

| Stage | Question | How to Execute |
|---|---|---|
| Process start | From process creation until process begins running | Record timestamp immediately before start command |
| Application ready | When is the application ready to accept traffic | Wait for readiness probe success |
| First request | How long does the first business request take | Send request after readiness and record separately |
| Warm-up | How does behavior shift as runtime/caches stabilize | Send identical warm-up workload; exclude from steady-state |
| Steady-state | Latency/throughput once system stabilizes | Measure over a fixed time window |
| Shutdown | How long to stop and release resources | Send shutdown signal and record exit duration |

**Cold start** must be defined per experiment. A fresh container on a host with warm page cache is not a full cold machine boot. A fresh process hitting a pre-warmed database connection pool and remote cache is not a system-wide cold start either. State clearly what is reset: process/container, application cache, database cache, DNS, broker connections, or host.

For steady-state, send both JVM and native through the exact same warm-up requests. The JVM performs JIT compilation and may speed up after running for a while; Native Image does not use HotSpot JIT in the same way. Never skip JVM warm-up and compare it to a stabilized native instance, nor omit business warm-up such as caches, connection pools, and schema loading on native.

If the product targets scale-to-zero or serverless, cold-start is critical and requires its own benchmark. If instances run continuously for days, steady-state throughput, tail latency, GC, and RSS usually carry more weight.

## 9. Repeatability Procedure and Order Balancing

A single run is easily skewed by CPU turbo boost, thermal throttling, background jobs, caches, network jitter, or database activity. Run multiple independent iterations and keep per-run data.

Recommended procedure:

1. Lock commit, dependencies, configuration, dataset, and workload.
2. Verify functional parity between JVM and native.
3. Start supporting hosts/containers and wait for stability.
4. Run JVM or native per the defined scenario; never run concurrently if sharing resources.
5. Execute warm-up using identical workload and duration.
6. Run the measurement window at identical arrival rate/concurrency and duration.
7. Save raw outputs, logs, metrics, configuration, and host state.
8. Stop the process/container and reset data/caches per protocol.
9. Run the other runtime.
10. Repeat for at least several independent iterations; add more if variance remains high.

To prevent one runtime from always running first on a cold machine or later with warmed caches, alternate run order. For example:

```text
Run 1: JVM -> Native
Run 2: Native -> JVM
Run 3: JVM -> Native
Run 4: Native -> JVM
Run 5: JVM -> Native
```

You can randomize order instead of strictly alternating. Either way, record run order and rest intervals. If the benchmark modifies data, restore the exact same snapshot before every run.

Choose warm-up and measurement durations according to the application. Small services might start with 30–60 seconds of warm-up and several minutes of measurement; long workloads or periodic caches/GC need longer windows. Do not treat example durations as universal standards. Inspect throughput/latency time series to confirm the measurement window has stabilized.

## 10. Measuring Startup to Readiness

Process creation time is not when the application is ready for traffic. Spring Boot Actuator exposes startup metrics such as:

- `application.started.time`: time taken to start the application.
- `application.ready.time`: time taken until the application is ready to service requests.

These two metrics help analyze internal startup. To measure end-to-end deployment experience, measure from container/process launch until the readiness probe succeeds. Keep the readiness endpoint, timeout, polling interval, and external dependency state identical for both runtimes.

Example readiness wait script on Linux:

```bash
#!/usr/bin/env bash
set -euo pipefail

start_ns=$(date +%s%N)
./service &
app_pid=$!

cleanup() {
  kill "$app_pid" 2>/dev/null || true
  wait "$app_pid" 2>/dev/null || true
}
trap cleanup EXIT

until curl --fail --silent http://127.0.0.1:8080/actuator/health/readiness >/dev/null; do
  if ! kill -0 "$app_pid" 2>/dev/null; then
    echo "Application exited before readiness" >&2
    exit 1
  fi
  sleep 0.1
done

ready_ns=$(date +%s%N)
awk -v start="$start_ns" -v ready="$ready_ns" \
  'BEGIN { printf "startup_to_ready_ms=%.2f\n", (ready-start)/1000000 }'
```

This script is a Linux example; adapt the launch command, readiness path, and process management to your application. For containers, capture the start timestamp right before `docker run`, and run the readiness probe from outside the container to include image startup and orchestration overhead when that is what you want to measure.

Do not rely solely on the JVM's "Started Application in … seconds" log if native is measured via an external readiness probe. Those two numbers cover different intervals. Pick one consistent milestone for comparison and optionally log internal metrics for explanation.

Repeat across multiple fresh processes/containers. Report median, min/max, or percentiles of startup-to-ready; never present the fastest run as representative.

## 11. Measuring Latency, Throughput, and Error Rate

For HTTP services, core metrics include:

- **Throughput:** completed requests per second (RPS), or messages processed per second.
- **Latency:** time from when the client sends a request until it receives the response.
- **Tail latency:** p95 and p99, showing the experience of slower requests.
- **Error rate:** rate of timeouts, HTTP 5xx, business errors, or incomplete requests.
- **Saturation:** queue depth, pool usage, thread count, CPU throttling, and connection wait.

Report at least p50, p95, and p99 alongside throughput and error rate. Mean can be helpful yet often masks tail latency. A runtime with higher throughput but spiking p99 or higher error rate is not necessarily better.

Test multiple load levels rather than just one:

1. **Low load:** establish baseline latency while the system has plenty of headroom.
2. **Expected load:** average expected production traffic.
3. **Peak load:** high load still within target range.
4. **Overload/limit test:** push load to locate saturation and observe how the system degrades.

Keep load profile and duration identical for each runtime. Use identical HTTP keep-alive, TLS, connection counts, request bodies, response bodies, and timeouts. Place the load generator on a separate host so it never bottlenecks results.

For example, with k6, the same script can run sequentially against two base URLs:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '3m',
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
};

export default function () {
  const url = __ENV.BASE_URL + '/api/orders/42';
  const response = http.get(url);
  check(response, {
    'status is 200': (r) => r.status === 200,
  });
}
```

This example uses an arrival rate of 200 requests/second for 3 minutes; adjust rate, VUs, endpoint, and duration to your workload. Run the same script with `BASE_URL` pointing sequentially to JVM and native. Watch dropped iterations, timeouts, and error rates; if the load generator fails to issue the configured rate, results do not reflect the intended offered load.

## 12. Measuring Memory and CPU Properly

### 12.1. RSS Is the Primary Process Footprint Metric

When comparing deployment-level memory, measure **resident set size (RSS)** or cgroup/container memory usage. RSS reflects memory pages currently resident for the process. For containers, record both current usage and peak usage over the same measurement window.

Do not compare JVM heap directly against Native Image heap to conclude which runtime uses less memory. A JVM process also holds metaspace, code cache, thread stacks, direct buffers, and native regions. Native Image also uses memory outside the Java heap for code, stacks, and runtime structures. Heap is only part of RSS.

You can record simultaneously:

| Metric | Meaning |
|---|---|
| Container/cgroup memory current | Memory currently used by the container |
| Container/cgroup memory peak | Highest memory during the measurement run |
| Process RSS | Memory pages resident for the process |
| JVM heap used/committed | JVM heap details |
| Native Image Java heap | Object heap managed by Native Image |
| Thread count/stack | Thread count and stack memory |
| Direct/off-heap buffers | Off-heap memory if used by the application |

RSS and cgroup memory are not identical. Cgroups may count page cache or other components depending on kernel/version configuration. Specify the metric source and use the same source for both runtimes.

### 12.2. CPU and GC

Measure CPU utilization over time and CPU time per request/message. CPU percentage can be misinterpreted without knowing how many cores the container quota grants; record allocated CPU cores and throttling time alongside utilization.

With JVM, collect GC logs, JFR, and Micrometer JVM metrics. Spring Boot Actuator can expose memory pool, GC, thread, process/system CPU, and HTTP request metrics. With Native Image, use runtime monitoring/metrics appropriate to your GraalVM version and the same required instrumentation level.

Comparing throughput alongside CPU consumption answers whether one runtime completes the same work with less CPU. Looking only at low CPU might just mean the service is processing fewer requests.

### 12.3. Do Not Forget Memory Limits and OOM

Apply identical container memory limits and swap policies. Record container restarts, OOM kills, `OutOfMemoryError`, GC pauses, and when peak memory occurs. A build with low average RSS that spikes past the limit during batch processing may not be viable for production.

Native Image offers multiple GC implementations and heap policies depending on GraalVM distribution/edition/architecture. Document GC and runtime options. If tuning GC or heap policy, create a separate tuned run while keeping workload and container limits constant.

## 13. Selecting Measurement Tools and Keeping Instrumentation Equivalent

No single tool measures every dimension. Choose tools by question:

| Goal | Possible Tools | Notes |
|---|---|---|
| HTTP load | k6, Gatling, JMeter, wrk | Run load generator outside the service host |
| Startup/readiness | Readiness probe, script timestamps, Actuator startup metrics | Use identical start/end milestones |
| Container CPU/memory | Docker stats, cgroup metrics, Prometheus | Keep sampling interval identical |
| JVM runtime | JFR, GC logs, Micrometer/JMX | Adds overhead; document when enabled |
| Native process | OS process metrics, cgroup, GraalVM runtime metrics/tooling by version | Pick equivalent process/container metrics |
| Java microbenchmarks | JMH | For isolated methods/components; does not replace service load tests |

Spring Boot Actuator and Micrometer expose JVM meters such as memory pools, garbage collection, threads, class loading, and JIT compilation, along with system/process metrics, startup metrics, and HTTP request observations. Enable identical instrumentation on both runtimes when using these meters in comparisons. If a metric exists only on JVM, use it to diagnose JVM rather than placing it beside a differently defined Native Image metric as if they were equivalent.

JMH is well suited for measuring small Java code paths while controlling warm-up, measurement iterations, and forks. It does not replace benchmarking an entire Spring Boot service over HTTP/brokers. Comparing JVM against a native executable requires a load harness sending the exact same workload to two independent processes. Never extrapolate production latency from a microbenchmark run in an IDE.

Instrumentation alters performance. JFR, profilers, debug logging, tracing exporters, and metrics scraping all add overhead. When aiming for production-like numbers, disable heavy profilers on both sides and leave only minimal identical instrumentation enabled. When profiling is needed to explain results, run a separate profiling pass, document overhead, and never mix those numbers into the baseline.

## 14. Separating Baseline, Tuning, and Profile-Guided Optimization

A fair comparison must state whether default or tuned configurations are being measured. GraalVM Native Image offers optimization levels and GC choices; the JVM also has GC, heap, JIT, and compiler options. Changing these flags affects throughput, latency, memory, and build time.

Proceed in passes:

### 14.1. Baseline

- Use identical source, dependencies, data, business config, and workload.
- Grant identical CPU/memory quotas.
- Use identical application config/production profile; keep each platform's default runtime options for the baseline and document all differences.
- Record all JVM flags, native build options, GC, heap policy, and container images.
- Do not enable PGO or special profiling on one side without a corresponding measurement.

The baseline answers: under our current deployment practices, how do the two runtimes differ?

### 14.2. Tuning

After the baseline, tune each runtime separately—for example adjusting JVM heap/GC or Native Image GC/heap/optimization level. Every change must be recorded as its own configuration and re-measured with the exact same dataset, load profile, and infrastructure.

Never change multiple variables at once. Changing GC, pool size, and connection limits simultaneously makes it impossible to tell which change drove the result. Change one small group, measure, keep or roll back, and only then test the next group.

### 14.3. PGO for Native Image

Profile-Guided Optimization (PGO) can improve throughput for certain applications. The general workflow builds an instrumented image, runs a representative workload to collect a profile, and rebuilds using that profile. Because PGO relies on workload data to guide optimizations, the profile must come from a request mix close to production.

With the Native Image CLI, the general flow looks like:

```bash
# Build an instrumented executable to collect a profile.
native-image --pgo-instrument -jar target/my-application.jar

# Run the instrumented executable under a representative workload; the default profile
# is written to default.iprof in the working directory.
./my-application

# Rebuild the image using the collected profile.
native-image --pgo -jar target/my-application.jar
```

This is a generic CLI example; with Maven/Gradle Native Build Tools, pass corresponding options via plugin configuration and verify the build output directory. Never reuse an old profile from a different commit, dependency set, or workload without verifying compatibility.

If including PGO in benchmarks:

- Report it as a separate result rather than merging into the native baseline.
- Use the same representative workload to generate the profile.
- Record GraalVM distribution/edition, version, build options, and profile file.
- Include profile-generation and rebuild costs if the question covers release costs.
- Compare against an appropriately warmed-up JVM under the same workload.

A profile captured from a single endpoint or skewed data can over-optimize native for that case while hurting other flows. PGO also depends on GraalVM edition and version; verify toolchain support.

## 15. Aggregating and Interpreting Results

Preserve raw data from every run. For each metric, compute per-run values and report median alongside dispersion (min/max, interquartile range, or an appropriate confidence interval). Never pool every request across runs into one giant bucket and ignore run-to-run variation.

For metrics where **lower is better** (startup, latency, RSS, CPU time), you can compute percentage change:

```text
Improvement (%) = (JVM - Native) / JVM * 100
```

For throughput, **higher is better**:

```text
Improvement (%) = (Native - JVM) / JVM * 100
```

For example, if JVM median startup-to-ready is 1.20 seconds and native is 0.45 seconds:

```text
(1.20 - 0.45) / 1.20 * 100 = 62.5%
```

This figure describes only the outcome under the documented benchmark conditions, not a guaranteed improvement for every application.

Results table template:

| Metric | JVM Median | Native Median | Change | Notes |
|---|---:|---:|---:|---|
| Startup-to-ready (ms) | — | — | — | Fresh process, same readiness probe |
| First request p95 (ms) | — | — | — | Measured separately after readiness |
| Steady-state p50 (ms) | — | — | — | Same request mix |
| Steady-state p95 (ms) | — | — | — | Same offered load |
| Steady-state p99 (ms) | — | — | — | Same offered load |
| Throughput (RPS) | — | — | — | Zero dropped iterations |
| Error rate (%) | — | — | — | Same error criteria |
| RSS median (MiB) | — | — | — | Same measurement window |
| RSS peak (MiB) | — | — | — | Same cgroup limit |
| CPU cores average | — | — | — | Include throttling |
| CPU time/request (ms) | — | — | — | Same workload |

When reading the table, place metrics side by side. If native lowers RSS while p99 rises, determine whether that trade-off is acceptable. If native starts faster yet delivers lower throughput under sustained load, deployment choices depend on workload shape and product goals.

Do not draw conclusions when error rates differ significantly, the load generator saturates, a run misses requests, containers suffer abnormal throttling, or data was not reset identically. Mark such runs invalid and repeat under the protocol; never silently drop unfavorable runs without documenting the reason.

## 16. Reproducible Benchmark Manifest

Every report should archive both results and the conditions that produced them. You can use YAML as a simple manifest:

```yaml
benchmark:
  name: spring-boot-jvm-vs-native
  commit: "<git-sha>"
  dataset: "orders-snapshot-2026-11"
  workload: "orders-read-write-mix-v2"
  runs: 5

application:
  springBoot: "<version>"
  java: "<version>"
  graalvm: "<version>"
  dependencyLockHash: "<sha256>"
  profile: "benchmark"

infrastructure:
  os: "linux"
  architecture: "amd64"
  cpuLimit: "2"
  memoryLimit: "1GiB"
  memorySwap: "1GiB"
  database: "<version-and-location>"
  broker: "<version-and-location>"

load:
  model: "constant-arrival-rate"
  ratePerSecond: 200
  warmup: "60s"
  measurement: "180s"
  requestMix: "orders-read-write-mix-v2"

runtime:
  jvm:
    image: "<image-digest>"
    options: "<record-all-flags>"
  native:
    image: "<image-digest>"
    buildOptions: "<record-all-options>"
```

Values in the manifest are placeholders or examples to replace with real data. Also save raw load-test outputs, metric exports, startup logs, GC/JFR logs if captured, image digests, and full command lines. Never store credentials, tokens, or customer data in manifests.

A benchmark is reproducible only when others know the exact artifact, data, configuration, environment, and load generation setup. Record dates/times, host, kernel, container runtime, tool versions, and run order to explain variations between runs.

## 17. Common Sources of Confounding Noise

| Skew | Why It Distorts Results | How to Address |
|---|---|---|
| JVM warmed up, native lacks business warm-up | Caches/connection pools differ | Run identical warm-up workload |
| Different dataset or cache state | DB/cache cost differs | Restore snapshot and reset per protocol |
| Different CPU/memory limits | One runtime gets more resources | Enforce identical cgroup quotas and record throttling |
| Running both processes concurrently on one host | Contention for CPU, memory bandwidth, and I/O | Run sequentially or on equivalent isolated hosts |
| Comparing JVM heap against native heap | Measuring different memory scopes | Use RSS/cgroup memory as the primary footprint metric |
| Measuring only mean latency | Hides slow requests | Report p50/p95/p99 and error rate |
| Load generator saturated | Fails to deliver full offered load | Isolate generator and monitor dropped iterations |
| Profiler enabled on one side only | Instrumentation adds asymmetric overhead | Disable in baseline or enable equivalently |
| Different dependencies/profiles | Execution paths and functionality differ | Audit lockfile, profiles, and functional parity |
| Cherry-picking the fastest run | Ignores variance | Repeat and report median/dispersion |
| PGO trained on a single scenario | Native over-optimizes for skewed workload | Use representative request mix and report separately |
| Undocumented base image/libc differences | Runtime dependencies and startup differ | Record image, libc, and OS/architecture |

Some sources of bias cannot be eliminated entirely. In those cases, document limitations clearly and avoid overclaiming causality. A benchmark measures a specific environment and workload; it does not automatically prove every deployment will yield identical results.

## 18. Pre-Publication Checklist

- [ ] Identical git commit and business source code.
- [ ] Identical Spring Boot/Framework versions and runtime dependencies.
- [ ] Documented GraalVM/JDK, build tools, and native build options.
- [ ] Identical dataset snapshot, schema, indexes, seed, and cache state.
- [ ] Identical Spring profile, feature flags, and business configuration.
- [ ] Identical database, broker, auxiliary services, and network path.
- [ ] Identical CPU/memory/swap limits, architecture, and replica count.
- [ ] Identical request mix, payloads, connection behavior, and load model.
- [ ] Verified functional parity prior to benchmarking.
- [ ] Separated startup, first request, warm-up, and steady-state.
- [ ] Ran multiple iterations and balanced/randomized run order.
- [ ] Measured p50/p95/p99, throughput, error rate, RSS, CPU, and peak memory.
- [ ] Confirmed load generator did not saturate.
- [ ] Documented runtime-specific options, GC, and PGO if applicable.
- [ ] Saved raw data, manifest, logs, and image digests.
- [ ] Explicitly stated limitations and any conditions that could not be held identical.

## References

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): JVM/system/process metrics, startup metrics, HTTP request observations, and task scheduling metrics.
- [GraalVM Native Image — Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/): Native Image heap, GC, throughput, latency, footprint, and off-heap memory.
- [GraalVM Native Image — Optimizations and Performance](https://www.graalvm.org/jdk25/reference-manual/native-image/optimizations-and-performance/): optimization levels, PGO, and performance flags.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): guide to reliable Java microbenchmarking, warm-up, measurement, and setup.
- [Docker — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/): CPU, memory, swap limits, and cgroup effects on containers.
- [Oracle Java — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): JVM options, unified logging, and JFR.

## Conclusion

Comparing JVM against GraalVM Native Image is trustworthy only when both execute the same source, runtime dependencies, data, business configuration, workload, and infrastructure. Measure startup-to-ready separately from first request and steady-state; report latency percentiles alongside throughput and error rate; use RSS or cgroup memory to compare footprint instead of putting JVM heap beside Native Image heap. Repeat multiple runs, archive manifests and raw data, and separate baselines from tuning/PGO passes. The resulting data empowers teams to choose the runtime suited to their Spring Boot workload and real deployment constraints.

# Writing a Decision Report Choosing JVM or Native Based on Functionality, Metrics, and Build Cost

Choosing JVM or GraalVM Native Image is an architectural and operational decision. A native executable typically offers advantages in startup time and memory footprint across many workloads. The JVM offers a JIT compiler, a flexible runtime ecosystem, and generally a simpler build pipeline. You cannot conclude one option is superior solely from startup time or binary size.

A defensible decision must answer four questions:

1. Do both options implement all functionality and meet compatibility requirements?
2. How do they differ when measuring startup, latency, throughput, CPU, and memory under identical conditions?
3. How much does the cost of building, testing, storing, and releasing native artifacts increase?
4. Are the runtime benefits large enough to offset build, maintenance, and operational costs?

This practice builds a decision report for a Spring Boot Order API service. The experiment compares three variants: regular JVM, JVM running Spring AOT-generated code, and GraalVM Native Image. The AOT-on-JVM variant isolates the impact of Spring AOT from the impact of native compilation.

## 1. Define the Decision to Be Made

Before benchmarking, state the decision scope clearly. For example:

> Choose the packaging format for the continuously running Order API in Kubernetes, with steady traffic, requiring p95 latency under 200 ms, rolling-deployment startup under 10 seconds, and container-level memory limits.

Another decision might target a short-lived job worker:

> Choose the runtime for a worker that scales from zero, typically processes a single job in a few seconds, needs to be ready in under one second, and has strict memory limits.

Two services both built with Spring Boot may arrive at different choices. Workload goals dictate which metrics carry value.

Document constraints before measuring:

- Required functionality and integrations.
- SLOs/SLAs for startup, latency, throughput, and error rate.
- CPU, memory, and replica limits.
- Deployment platforms: Linux/AMD64, Linux/ARM64, Windows, or macOS.
- Release frequency and number of platform artifacts to build.
- Observability, security, debugging, and incident response requirements.
- Required flexibility for plugins, dynamic class loading, and runtime configuration.

Do not change criteria after viewing results just to justify a preferred option.

## 2. Compare Three Variants to Isolate the Effect of AOT

Use three variants from the exact same source code and dependency graph:

| Variant | How It Runs | What We Want to Know |
| --- | --- | --- |
| Regular JVM | Executable JAR on the JVM, without Spring AOT generated initialization | Baseline of the current application |
| JVM + Spring AOT | JAR with AOT generated assets, running on the JVM with AOT enabled | Benefits of Spring AOT while keeping the JVM runtime |
| Native Image | Executable produced by GraalVM Native Image | Benefits and limitations of native compilation |

If you compare only regular JVM against native, gains from Spring AOT may be misattributed to the native executable. The second variant identifies the portion of startup improvement coming from preparing the ApplicationContext at build time.

Spring Boot can run an application on the JVM using AOT-generated code when `spring.aot.enabled=true` is set. The JAR must be built to include AOT assets. With Maven, the `native` profile is the common way to trigger AOT processing; with Gradle, the GraalVM Native Image plugin applies the required AOT tasks.

### Sample Builds

With Maven, regular JVM baseline:

~~~bash
./mvnw clean package
java -jar target/orders-api.jar
~~~

Build the JAR with Spring AOT assets and run AOT on the JVM:

~~~bash
./mvnw -Pnative package -DskipTests
java -Dspring.aot.enabled=true -jar target/orders-api.jar
~~~

Build the native executable:

~~~bash
./mvnw -Pnative native:compile
~~~

With Gradle:

~~~bash
# Regular JVM
./gradlew clean bootJar

# Run AOT then package JAR for AOT-on-JVM
./gradlew processAot bootJar

# Native executable
./gradlew nativeCompile
~~~

Specific tasks and profiles depend on your project's Maven/Gradle configuration. Inspect output to ensure the AOT JAR actually contains generated assets and the native build uses the exact GraalVM version. Do not benchmark a plain JAR with the AOT runtime property enabled without generated code.

## 3. Set Functional Gates Before Scoring

Functional compatibility is a mandatory prerequisite, not a criterion that can be offset by startup or memory scores.

Run the same test suite across all three variants, covering:

- Spring ApplicationContext initialization and all required beans.
- REST APIs, validation, serialization/deserialization, and error handling.
- Database drivers, connection pools, and transactions.
- HTTP clients, message brokers, or external integrations.
- Security filters, authentication, authorization, and TLS.
- Reflection, resources, dynamic proxies, JNI, or third-party libraries in use.
- Health/readiness endpoints, graceful shutdown, and context propagation.
- Supported profiles/configurations in the deployment design.

| Hard Gate Condition | Regular JVM | JVM + AOT | Native |
| --- | --- | --- | --- |
| Required unit and integration tests | Pass/Fail | Pass/Fail | Pass/Fail |
| Critical business flows | Pass/Fail | Pass/Fail | Pass/Fail |
| Dependencies and native integrations | Pass/Fail | Pass/Fail | Pass/Fail |
| Security and TLS | Pass/Fail | Pass/Fail | Pass/Fail |
| Health/readiness/shutdown | Pass/Fail | Pass/Fail | Pass/Fail |
| Runs on target platform | Pass/Fail | Pass/Fail | Pass/Fail |

If an option fails a hard gate, mark it **disqualified**. Never award performance points to compensate for functional bugs, security gaps, or missing platform support.

Spring Boot recommends continuing to run most unit/integration tests on the JVM for fast feedback, then focusing native tests on AOT processing, reachability hints, and code paths with differing behavior. You can run AOT-generated code on the JVM before native compilation to catch AOT errors at lower cost.

## 4. Design a Representative Workload

Benchmarks are only meaningful if the workload mirrors how the application is used in production.

For the Order API, select at least three groups:

| Workload Group | Example Requests | Purpose |
| --- | --- | --- |
| Read operations | Fetch order, search by status | Measure latency and throughput of common queries |
| Write operations | Create order, update status, transactions | Measure CPU, database interaction, and error rate |
| Integrations | Call payment/partner service | Measure network impact, client instrumentation, and timeouts |

Define upfront:

- Read/write/integration request ratios.
- Payload sizes and data distribution.
- Cache hit/miss ratios.
- Database connection counts and connection pool limits.
- Concurrency, request rate, and run duration.
- Intentional error rate in the workload.
- Dataset and database state before each measurement.

Do not use an endpoint returning a static string to represent the entire system if production involves databases, serialization, and external calls. A trivial endpoint is only suitable for measuring HTTP framework overhead in a narrow slice.

Example benchmark SLOs:

~~~text
Functional tests: 100% pass
HTTP error rate: < 0.5%
p95 latency: < 200 ms at 200 requests/second
p99 latency: < 400 ms at 200 requests/second
Startup to ready: < 10 seconds
Container memory: < 512 MiB at target load
Sustainable throughput: >= 1,000 requests/second
~~~

The numbers above are examples only. Replace them with your service's real SLOs and record the criteria version in the report.

## 5. Control Experimental Conditions

Keep the following factors identical across variants:

- Same source commit, dependency versions, and business configuration.
- Same OS, CPU model, architecture, and kernel when comparing runtimes.
- Same CPU quota, memory limit, container runtime, and network path.
- Same database, dataset, pool size, and cache state.
- Same request mix, payloads, concurrency, and load generator.
- Same replica count or scaling rules when comparing a single instance.
- Same logging level, metrics/tracing exporters, and sampling policies.

Do not run JVM on a 32-CPU machine and native on an 8-CPU machine. Do not give JVM a large heap limit while capping native with a lower container limit. If GC, heap, or thread configs differ for production tuning, document each configuration explicitly and also run an apples-to-apples baseline comparison under equivalent conditions.

### Separate Cold Start from Steady State

These two measurements answer different questions:

- **Cold start:** how long from launching the process/container until the service genuinely accepts requests.
- **Steady state:** how the application handles sustained load after startup and warm-up.

The JVM performs JIT compilation and may improve throughput once hot code is compiled. A native executable lacks a HotSpot-style JIT compiler, yet is still affected by CPU caches, filesystem caches, connection pools, and lazy initialization steps. Therefore, never compare a warmed-up JVM against a freshly started native process.

## 6. Measure Startup and Time-to-Ready

Spring Boot Actuator exposes two startup metrics:

- `application.started.time`: time the application took to start.
- `application.ready.time`: time from start until the application is ready to service requests.

These two metrics are useful for comparing startup inside Spring. However, platform readiness can also depend on container startup, networking, probe intervals, and load balancers. Also measure externally: from container creation until the first successful business response.

Measurement procedure:

1. Start a fresh process for each measurement.
2. Record the process/container start timestamp.
3. Poll the readiness endpoint at a fixed interval.
4. Record the timestamp of readiness success and first successful business request.
5. Stop the process, wait for resources to be released, and run the next trial.
6. Repeat at least 20 times per variant; increase trials if results fluctuate widely.
7. Report median, p95, and min/max; do not pick only the fastest run.

Measure image pull time separately if real deployments must fetch a new image. Do not fold image pull time into process startup without noting it, as that is artifact distribution cost rather than Spring startup time.

| Startup metric | Regular JVM | JVM + AOT | Native |
| --- | ---: | ---: | ---: |
| Median ready time | ... | ... | ... |
| p95 ready time | ... | ... | ... |
| Median first successful request | ... | ... | ... |
| p95 first successful request | ... | ... | ... |

If the service uses lazy initialization, readiness success does not necessarily prove all dependencies are ready. Use the same readiness policy and execute a real business request after startup.

## 7. Measure Throughput, Latency, and Error Rate

Measure steady state after a fixed warm-up period. An HTTP script can use k6:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 40,
  duration: '10m',
  thresholds: {
    http_req_failed: ['rate<0.005'],
    http_req_duration: ['p(95)<200', 'p(99)<400']
  }
};

export default function () {
  const response = http.get(
    __ENV.BASE_URL + '/api/orders/benchmark'
  );

  check(response, {
    'status is 200': (res) => res.status === 200
  });
}
~~~

Run the same script, dataset, and load generator for each variant. Test multiple load levels—such as 50, 100, 200, and 400 requests/second—rather than measuring only a single point.

Collect:

- Actual requests/second.
- p50, p95, and p99 latency.
- Error rate and timeouts.
- Number of queued or rejected requests.
- CPU utilization and cores consumed.
- Database connection wait times, pool saturation, and external dependency latency.

Step up load until one of the thresholds is breached: p95, p99, error rate, CPU, or memory. Maximum throughput is meaningful only while SLOs remain satisfied. A variant with higher throughput but elevated error rates or breached p99 is not considered faster for production.

## 8. Measure CPU and Processing Efficiency

Absolute CPU usage can mislead if one variant processes more requests than the other. Normalize by completed work.

Metrics to record:

- Average and peak CPU cores.
- CPU seconds per 1,000 successful requests.
- Throughput at the same CPU quota.
- p95/p99 at the same request rate.
- CPU throttling inside the container.
- GC CPU and pause times if applicable.

For example, native might use 0.9 cores to process 1,000 requests while JVM uses 0.8 cores. If native uses less memory but consumes more CPU, the outcome depends on resource limits and unit costs on your platform.

Do not use host CPU percentage when two processes run on hosts with different core counts. Prefer core-seconds or CPU time measured from identical containers/cgroups.

## 9. Measure Memory Properly

Do not compare JVM heap against Native Image heap as though they were the same quantity. JVM heap is only one portion of memory; RSS and container memory also include code, metadata, thread stacks, direct buffers, native allocations, and shared libraries.

| Metric | Meaning |
| --- | --- |
| RSS idle | Resident memory when the service is ready with near-zero requests |
| RSS steady state | Resident memory while handling steady workload |
| Peak RSS | Highest RSS level during the measurement window |
| Container/cgroup memory | Memory charged against the container's quota |
| JVM heap used/committed | Present only on JVM variants; for internal diagnostics |
| Native heap/GC metrics | Use only when supplied by runtime/binder; does not replace RSS/cgroup |
| OOM/restart count | Identifies whether a variant hit limits or was killed by the system |

Measure memory at idle and at identical request rates. A native executable with low idle RSS that climbs rapidly under load may not yield the expected overall savings.

Comparison rules:

- Use the same container memory limit.
- Use the same in-flight request volume and steady-state duration.
- Track peaks and percentiles, not a single snapshot.
- Document whether memory includes sidecars, proxies, and agents.
- Keep metrics/tracing configuration identical because telemetry consumes memory too.

If the JVM is configured with an oversized `-Xmx`, RSS can remain well below the maximum heap; never use Xmx as a measure of actual memory usage.

## 10. Measure Build and CI/CD Pipeline Cost

Native Image builds typically consume more CPU, memory, and time than JVM packaging. Native builds may require high-RAM runners, OS toolchains, and a separate job per platform.

Record for each pipeline:

- Clean build duration and incremental build duration.
- Native Image compilation duration.
- Builder peak RSS or memory limit.
- CPU time, thread count, and queue wait time.
- Build failure/retry rate.
- Number of OS/architecture targets required.
- Native testing time and publish time.
- Artifact/container image size and storage/transfer costs.

GraalVM Build Output reports build resources, peak RSS, CPU load, stage durations, and build artifacts. Use that output to determine how much RAM/CPU native builds need, rather than recording only total wall-clock time.

Native pipelines may require an OS/architecture runner matrix, dedicated tests for reflection/resources/JNI/serialization, GraalVM/Native Build Tools version management, reachability metadata maintenance, ABI/libc/CPU target handling, and rebuilding multiple images for security patches. Counting only compile time while ignoring tests, retries, runners, artifacts, and engineering effort underestimates total cost.

## 11. Model Total Cost

Break down costs across the lifecycle:

\[
C_{\text{total}} =
C_{\text{CI}} +
C_{\text{runtime}} +
C_{\text{distribution}} +
C_{\text{operations}}
\]

Where:

- `C_CI`: runner minutes, native build workers, caches, and retries.
- `C_runtime`: CPU, memory, replica count, and uptime.
- `C_distribution`: image storage, registry transfer, and artifact retention.
- `C_operations`: effort to maintain pipelines, hints, platform matrices, and incident response.

Formula for estimating CI cost:

\[
C_{\text{CI}} =
N_{\text{builds}}
\times
\sum_{i=1}^{n}
\left(
\frac{T_i}{60}
\times
R_i
\right)
\]

`T_i` is the duration in minutes of platform job i; `R_i` is the runner rate per minute. Use actual rates from your CI provider and runner tier. If jobs run in parallel, total runner-minutes still equals the sum of billable time across every job.

Runtime cost must be based on the number of replicas actually required to meet SLOs. A native replica might use less memory yet achieve lower throughput, requiring more replicas or CPU. Do not assume lowering per-instance RSS automatically lowers the cloud bill.

## 12. Example Benchmark Data

The table below contains **hypothetical data to illustrate the analysis method**, not default benchmarks for Spring Boot or GraalVM. Assume all three variants passed every functional gate and were measured on the same host, container limits, dataset, and workload.

| Metric | Regular JVM | JVM + AOT | Native |
| --- | ---: | ---: | ---: |
| Median ready time | 2.75 s | 2.10 s | 0.58 s |
| RSS idle | 210 MiB | 198 MiB | 92 MiB |
| RSS at 200 req/s | 390 MiB | 382 MiB | 248 MiB |
| p95 at 200 req/s | 96 ms | 94 ms | 103 ms |
| p99 at 200 req/s | 185 ms | 178 ms | 196 ms |
| Max throughput within SLO | 1,280 req/s | 1,300 req/s | 1,160 req/s |
| CPU core-seconds / 1,000 requests | 0.82 | 0.79 | 0.87 |
| Clean build duration | 1.6 min | 2.4 min | 12.5 min |
| Peak builder RSS | 1.4 GiB | 1.8 GiB | 7.4 GiB |

### Reading the Results

- Spring AOT improved ready time from 2.75 seconds to 2.10 seconds even while remaining on the JVM.
- Native achieved the lowest ready time and reduced idle/steady-state RSS in this example.
- JVM + AOT delivered slightly higher throughput and lower p95 than native at the same 200 req/s.
- Native used more CPU per 1,000 requests in this illustrative dataset.
- Native builds took significantly longer and required much higher peak builder memory.

Do not conclude that native always has lower throughput. Results depend on workload, GraalVM version, optimizations, GC, PGO, CPU target, and libraries. The data above describes an illustrative measurement only.

## 13. Scoring Matrix and Decision

Score options only after they pass all functional gates. Assign weights according to service goals; score 1–5 where 5 is best. For cost and complexity criteria, a higher score means less expensive or easier to operate.

Example for a continuously running Order API:

| Criterion | Weight | JVM + AOT | Native |
| --- | ---: | ---: | ---: |
| Startup/ready time | 15 | 3 | 5 |
| Steady-state throughput | 15 | 5 | 4 |
| p95 latency | 20 | 5 | 4 |
| RSS at target load | 15 | 2 | 5 |
| CPU per request | 10 | 5 | 4 |
| CI/build cost | 15 | 5 | 1 |
| Operational complexity | 10 | 5 | 3 |
| **Total weight** | **100** |  |  |

Calculate weighted score:

\[
S = \frac{\sum_i w_i \times s_i}{100}
\]

With the example scores:

- JVM + AOT: 4.25/5.
- Native: 3.75/5.

In this hypothetical workload, JVM + AOT is the initial recommendation for the continuously running Order API: 2.10 s startup still meets the 10-second threshold, throughput and p95 are better, and CI and operational costs are lower.

Native still holds clear advantages in startup and memory. If the workload shifts to a scale-to-zero worker requiring sub-second ready time or a container memory limit under 300 MiB at target load, JVM + AOT could fail the hard gate while native passes. In that case, the decision must switch to native despite a lower average score in the previous matrix.

### Weight Sensitivity Testing

Do not let a single arbitrary set of weights dictate architecture. Test at least two scenarios:

- **Throughput-first:** increase weights for throughput, p95, and CPU/request for long-lived services.
- **Startup/memory-first:** increase weights for ready time, RSS, and replica density for short-lived or scale-to-zero workers.

If the recommendation flips from small weight adjustments, the report must note that the decision is sensitive to priorities and requires additional data. If a hard SLA eliminates an option, do not use total score to obscure that result.

## 14. When Should Each Option Be Chosen?

### Regular JVM or JVM + AOT

Prefer the JVM when:

- The service is long-lived, giving JIT enough time to optimize the workload.
- Steady-state throughput or latency is the primary criterion.
- Libraries rely on dynamic class loading, Java agents, or runtime behaviors hard to port to Native Image.
- Releases are frequent and native build cost slows feedback.
- Familiar debugging, profiling, and ecosystem tooling are needed.

Consider JVM + AOT when startup needs improvement while keeping the JVM runtime. AOT imposes constraints on classpath, bean graphs, profiles, and build-time conditions; test against actual deployment configurations.

### GraalVM Native Image

Prefer native when:

- Cold start or time-to-ready is a hard requirement.
- Memory footprint dictates workload density or replica count.
- Services/workers are short-lived and frequently scale from zero.
- Dependencies and functionality are verified compatible with Native Image.
- The organization has mature CI runners, native testing, and metadata processes.

Native Image supports optimization levels and PGO; for CPU-bound workloads, you can benchmark PGO after establishing a stable baseline. PGO requires an instrumented build and representative profiling workload, so include profile collection in the release process.

### The Entire System Does Not Need One Uniform Runtime

A system can use native for scale-to-zero APIs, JVM + AOT for services needing moderate startup improvements, and regular JVM for long-running CPU-bound workers. Make decisions at the service/workload level to avoid migrating an entire platform for a localized benefit.

## 15. Decision Report Template

Use this structure to turn benchmarks into a reviewable decision:

~~~text
DECISION REPORT: JVM vs GRAALVM NATIVE IMAGE

1. Executive summary
   - Service:
   - Workload:
   - Recommended runtime:
   - Decision owner:
   - Date / source commit:

2. Requirements and hard gates
   - Functional test results:
   - Security / integration compatibility:
   - Startup SLO:
   - Latency / throughput SLO:
   - Memory / CPU limits:
   - Supported OS / architecture:

3. Variants
   - Regular JVM:
   - JVM + Spring AOT:
   - GraalVM Native Image:
   - JDK / GraalVM / Spring Boot versions:

4. Measurement methodology
   - Hardware / container limits:
   - Dataset and request mix:
   - Warm-up and run duration:
   - Repetitions and percentile method:
   - Metrics and tools:

5. Results
   - Ready time:
   - p50 / p95 / p99:
   - Throughput / error rate:
   - CPU per successful request:
   - RSS / cgroup memory:
   - Build duration / peak builder memory:

6. Cost model
   - CI runner cost:
   - Runtime compute:
   - Artifact / image storage:
   - Engineering and operational cost:

7. Decision matrix
   - Criteria and weights:
   - Scores:
   - Sensitivity scenarios:

8. Recommendation
   - Chosen runtime:
   - Why it meets hard gates:
   - Trade-offs accepted:
   - Risks and mitigations:

9. Rollout and review
   - Canary scope:
   - Rollback condition:
   - Metrics to watch:
   - Re-evaluation trigger:
~~~

The report must archive raw data, benchmark scripts, configs, build logs, and the source commit so others can reproduce it. Do not save only the final scorecard.

## 16. Rollout, Production Validation, and Re-Evaluation Triggers

Lab benchmarks are the basis for selection, not final proof of production cost. After choosing:

1. Deploy a small canary with the same resource limits and traffic policies.
2. Monitor startup/ready time, p95/p99, throughput, CPU, RSS/cgroup memory, and error rate.
3. Compare identical time windows and workloads against the current version.
4. Inspect autoscaling, rollout duration, crash/restart counts, and graceful shutdown.
5. Record build duration, retries, and release time in CI.
6. Expand rollout only when hard SLOs and functional checks pass.
7. Retain the rollback artifact and procedure to revert to the previous runtime.

Re-evaluate whenever major changes occur in Spring Boot, GraalVM, JDK, dependencies, traffic profile, CPU architecture, cloud pricing, or CI platform. A new dependency might slow down or break native builds; a new JDK might improve the JVM baseline; a shifting workload might alter memory/throughput trade-offs.

## 17. Practice Exercise: Write a Report for the Order API

Use a Spring Boot application with a REST API, a database, an HTTP client calling a partner service, and Actuator.

### Part A — Prepare Three Variants

1. Build and run the regular JVM JAR.
2. Build AOT assets and run on the JVM with `spring.aot.enabled=true`.
3. Build the native executable with GraalVM.
4. Keep the same commit, dependency versions, endpoints, and business configuration.
5. Record every difference in JVM options, GC, Native Image arguments, and container base images.

### Part B — Functional Gates

1. Run the same unit/integration test suite across all three variants.
2. Verify database transactions, serialization, security, and the partner HTTP client.
3. Verify health/readiness, graceful shutdown, and logging.
4. Run native tests for reflection, resources, proxies, serialization, or JNI if used by the application.
5. Disqualify any option failing mandatory functionality from scoring.

### Part C — Benchmark

1. Measure at least 20 cold starts per variant.
2. Measure ready time and first successful request.
3. Warm up for the same duration.
4. Run loads of 50, 100, 200, and 400 req/s using the same k6 script.
5. Collect p50/p95/p99, throughput, error rate, CPU core-seconds, and RSS.
6. Record native-image builder peak RSS and total CI duration.
7. Repeat experiments if host noise or high variance occurs.

### Part D — Report and Decision

1. Populate the comparison table with raw data.
2. Identify which options pass all hard gates.
3. Calculate CI cost by build volume and platform count.
4. Estimate runtime cost by replicas needed to satisfy SLOs.
5. Choose weights and compute decision scores.
6. Test throughput-first and startup/memory-first scenarios.
7. Write the recommendation, trade-offs, rollout plan, and rollback conditions.
8. State clearly what data is still missing and how it will be collected in a production canary.

### Self-Check Questions

1. Why compare regular JVM, JVM + AOT, and native instead of only two variants?
2. How must functional compatibility be enforced as a hard gate?
3. How does `application.ready.time` differ from the first successful request timestamp?
4. Why must cold start be separated from steady-state benchmarks?
5. Why cannot JVM heap substitute for RSS or cgroup memory when comparing against native?
6. Which SLOs must maximum throughput remain tied to?
7. Why normalize CPU time per successful request?
8. What factors contribute to native build cost beyond compilation time?
9. Why might reducing memory per replica fail to reduce the runtime bill?
10. When is JVM + AOT a sensible middle-ground option?
11. When do hard startup/memory SLOs make native mandatory?
12. Why test weight sensitivity in the decision matrix?
13. What changes require re-evaluating a JVM/native decision report?

**Passing criteria:** build all three comparison variants; define and thoroughly verify hard functional gates; design controlled cold-start and steady-state benchmarks; measure startup, latency, throughput, error rate, CPU, RSS, and native build costs; calculate CI/runtime costs; build a weighted decision matrix with sensitivity analysis; and finally produce a data-backed recommendation report with trade-offs, rollout, and rollback plans.

## Official Documentation

- Spring Boot — Metrics and Application Startup Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Boot — Testing GraalVM Native Images: https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html
- Spring Boot — Ahead-of-Time Processing With the JVM: https://docs.spring.io/spring-boot/reference/packaging/aot.html
- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/4.2/reference/packaging/native-image/advanced-topics.html
- Spring Boot — Maven Ahead-of-Time Processing: https://docs.spring.io/spring-boot/maven-plugin/aot.html
- Spring Boot — Gradle Ahead-of-Time Processing: https://docs.spring.io/spring-boot/gradle-plugin/aot.html
- GraalVM — Optimizations and Performance: https://www.graalvm.org/jdk25/reference-manual/native-image/optimizations-and-performance/
- GraalVM — Native Image Build Output: https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/
- GraalVM — Native Image Basics: https://www.graalvm.org/latest/reference-manual/native-image/basics/

# Maintaining Functional and Performance Comparisons Across JVM, JVM AOT, and Native

## 1. Purpose and Scope of Comparison

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring Boot uses **Spring Ahead-of-Time (AOT)** to prepare initialization code and metadata, allowing the application to run in three ways: standard JVM, JVM using generated Spring AOT code, or GraalVM Native Image. Each execution mode has distinct characteristics for startup, runtime, memory, and compatibility.

When upgrading Spring Boot, JDK/GraalVM, or dependencies, the team must maintain a repeatable comparison suite. The goal is to answer two independent questions:

- **Functionality:** do all three execution modes exhibit identical business behavior and API contracts under the same configuration?
- **Performance:** under the same workload and resource limits, how do startup, throughput, latency, CPU, and memory compare across modes?

This lesson clearly defines the three modes, how to build the artifacts, functional parity verification, benchmark design, and keeping baselines across upgrades.

After this lesson, learners can:

1. Distinguish standard JVM, JVM running Spring AOT, and GraalVM Native Image.
2. Explain why JVM AOT still uses the JVM runtime and JIT compiler.
3. Produce all three variants from the same source revision and dependency graph.
4. Control build-time profiles/conditions to avoid comparing mismatched configurations.
5. Design a test suite verifying functionality across all three modes.
6. Compare startup, cold request, warm throughput, latency, and memory.
7. Choose appropriate benchmarks for HTTP services and small code paths.
8. Control CPU, memory, containers, datasets, and downstream services.
9. Analyze differences caused by JIT warm-up, GC, image size, and static analysis.
10. Store benchmark provenance, baselines, and regression gates per release.

> **Rule:** confirm functional parity before comparing speed. Every measurement run must record source, build mode, runtime, platform, configuration, workload, and resource limits.

## 2. Three Modes to Distinguish

### 2.1. Standard JVM

This is the familiar way to run Spring Boot:

~~~bash
java -jar orders-service.jar
~~~

Spring builds and configures the `ApplicationContext` at runtime based on the process classpath and environment. The JVM loads classes on demand, executes bytecode, and compiles hot methods using the JIT compiler.

Typical characteristics:

- Classpath and many configuration decisions are resolved when the application runs.
- JIT requires warm-up time and optimizes based on observed runtime behavior.
- Can use dynamic class loading, reflection, and flexible runtime mechanisms within JVM limits.
- Startup and memory depend on JDK, GC, heap options, classpath, and workload.

This is the traditional JVM baseline for comparison against the other two modes.

### 2.2. JVM Running Spring AOT Code

**JVM AOT** in this lesson means the application has undergone Spring AOT processing, yet still runs via the `java` command on the JVM:

~~~bash
java -Dspring.aot.enabled=true -jar orders-service.jar
~~~

Spring AOT analyzes the `ApplicationContext` at build time and generates initialization/bean-definition code along with required hints. When `spring.aot.enabled=true` is set, Spring Boot uses the generated AOT code to initialize the context.

Understand the exact scope:

- Spring AOT optimizes Spring's startup and configuration phase.
- Application bytecode still runs on the JVM.
- The JVM still has the JIT compiler, GC, class loading, and JDK runtime services.
- JVM AOT is not a native executable and does not mean all Java methods were precompiled to machine code before launch.
- Classpath and bean decisions are fixed at build time per Spring AOT constraints.

Spring Boot supports running an AOT-processed application on the JVM via `spring.aot.enabled=true`. This mode is useful for measuring Spring AOT gains and inspecting generated code without waiting for `native-image` compilation. [Spring Boot — Ahead-of-Time Processing With the JVM](https://docs.spring.io/spring-boot/reference/packaging/aot.html).

### 2.3. GraalVM Native Image

Native Image uses AOT-generated assets to compile the application into a standalone executable for the target OS/architecture. At runtime, the process needs no JVM to execute bytecode and does not use HotSpot JIT as in JVM modes.

Characteristics:

- Static analysis identifies code reachable from entry points.
- Reflection, resources, serialization, dynamic proxies, and JNI require appropriate metadata/hints.
- Classpath is fixed at build time.
- The executable is tied to a specific platform/toolchain.
- No lazy class loading like a standard JVM.
- Runtime, GC, startup, and memory behavior differ from the JVM.

Spring AOT is a required preparation step for the Spring `ApplicationContext`; the Native Image compiler continues analyzing and producing the executable. [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html).

### 2.4. Comparison Table

| Attribute | Standard JVM | JVM + Spring AOT | Native Image |
| --- | --- | --- | --- |
| Runnable artifact | Executable JAR/classes | JAR with AOT-generated assets | Native executable |
| Spring context setup | Runtime parsing/configuration | Uses Spring AOT generated code | Uses Spring AOT generated code |
| Runtime engine | JVM | JVM | GraalVM Native Image runtime |
| JIT compiler | Yes | Yes | No HotSpot JIT |
| GC | JVM GC | JVM GC | Native Image GC chosen at build time |
| Classpath | Runtime classpath | Fixed per AOT build | Fixed inside image |
| Bean conditions | Evaluated at runtime | Evaluated during AOT processing | Evaluated during AOT processing |
| Reflection/resources | Flexible JVM runtime support | JVM runtime still supports, AOT has limits | Requires appropriate reachability metadata/hints |
| OS/architecture | JAR is generally portable per JDK | JAR is generally portable per JDK | Executable per target platform |
| Primary measurement focus | JIT steady state and flexibility | Spring AOT startup on JVM | Cold start, footprint, and native throughput |

Do not conclude Native Image is always faster than the JVM across every workload. Native Image typically wins on startup and memory footprint in many apps; the JVM can achieve higher throughput after JIT warm-up. Results depend on the application, runtime options, GC, PGO, CPU, and traffic mix.

## 3. Producing All Three Variants from the Same Source

### 3.1. Lock Source and Dependency Graph

Before building, record:

- Git commit or source revision.
- Spring Boot/Spring Framework versions.
- JDK vendor/version and GraalVM distribution/version.
- Maven/Gradle wrapper and Native Build Tools plugin versions.
- Dependency lock/BOM and resolved dependency graph.
- Build profile, environment variables, and system properties used during AOT processing.
- OS, architecture, libc, and CPU baseline for the native build.

Never compare three executables built from three different commits and attribute all differences to the runtime mode.

### 3.2. Maven: Build a JAR with AOT Assets

If the project uses `spring-boot-starter-parent`, the Spring Boot Maven Plugin's `native` profile activates `process-aot` and prepares Native Build Tools configuration.

~~~bash
./mvnw clean package
./mvnw -Pnative clean package
~~~

The JAR built with `-Pnative` contains AOT-generated assets. You can use that same JAR to run both JVM modes:

~~~bash
java -jar target/orders-service.jar
~~~

~~~bash
java -Dspring.aot.enabled=true -jar target/orders-service.jar
~~~

The first command runs standard JVM; the second tells Spring to use AOT-generated initialization code. When running AOT mode, verify the JAR actually contains generated assets.

To build the native executable with Native Build Tools, use the plugin configuration and `native` profile matching your project:

~~~bash
./mvnw -Pnative native:compile
~~~

In some Spring Boot/Buildpacks setups, the pipeline may use `spring-boot:build-image` with the `native` profile. Pick one explicit build path and record the exact command in the benchmark report. [Spring Boot Maven AOT Plugin](https://docs.spring.io/spring-boot/maven-plugin/aot.html).

### 3.3. Gradle: Producing JVM AOT Mode

To run Spring AOT on the JVM without creating a native executable, apply the `org.springframework.boot.aot` plugin:

~~~kotlin
plugins {
    id("org.springframework.boot") version "4.2.0"
    id("org.springframework.boot.aot")
    java
}
~~~

Build AOT assets and the JAR:

~~~bash
./gradlew processAot bootJar
~~~

Then run:

~~~bash
java -jar build/libs/orders-service.jar
java -Dspring.aot.enabled=true -jar build/libs/orders-service.jar
~~~

The first command uses standard JVM mode; the second uses Spring AOT on the JVM. Inspect startup output to confirm the application entered AOT-processed mode.

### 3.4. Gradle: Building Native Image

When the GraalVM Native Image plugin is applied, Spring Boot automatically configures AOT tasks and `nativeCompile` consumes `processAot` output:

~~~kotlin
plugins {
    id("org.springframework.boot") version "4.2.0"
    id("org.graalvm.buildtools.native") version "1.1.18"
    java
}
~~~

Build the native executable:

~~~bash
./gradlew nativeCompile
~~~

The executable is typically placed in `build/native/nativeCompile/`. Versions of Spring Boot and Native Build Tools in examples are illustrative; pin compatible versions for your project. [Spring Boot Gradle AOT Plugin](https://docs.spring.io/spring-boot/gradle-plugin/aot.html).

### 3.5. Ensure All Three Modes Use the Same AOT Configuration

Spring AOT prepares bean definitions at build time. Conditions affecting bean presence, such as `@Profile` or `@ConditionalOnProperty`, are evaluated during AOT processing. Therefore:

- Select profiles and bean-affecting properties before running `processAot`.
- Record environment/system properties used during the AOT build.
- Do not change a condition at runtime expecting AOT mode to create additional beans.
- Use the same AOT-generated assets when running JVM AOT and building Native Image.
- If you must compare multiple deployment profiles, build separate AOT artifacts for each valid profile.

Spring Boot explicitly states that the classpath and bean set are determined at build time when using AOT. [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/reference/packaging/aot.html).

## 4. Functional Parity Is the Gate Before Benchmarking

### 4.1. Define a Shared Contract

Before measuring performance, establish a service contract:

- Endpoints, HTTP methods, and request schemas.
- Response statuses, body schemas, and headers.
- Validation rules and error mapping.
- Authentication/authorization.
- Transaction boundaries and side effects.
- Database schema, migration version, and isolation level.
- Message topics, serialization formats, and delivery semantics.
- Cache keys, TTLs, and eviction behavior.
- Timeouts, retries, idempotency, and circuit-breaker behavior.
- Health/readiness behavior and graceful shutdown.

All modes must run the same contract, data, and dependency versions. If Native Image does not support a dynamic feature supported on standard JVM, resolve compatibility or document the limitation before evaluating performance.

### 4.2. Build a Canonical Test Dataset

Use a versioned input suite covering:

- Normal valid requests.
- Boundary values and large payloads.
- Missing fields, nulls, and invalid values.
- Unicode, timezones, and locales.
- Date/time edge cases.
- Serialization/deserialization of polymorphic types if used.
- Authentication success/failure.
- Downstream timeouts, connection errors, and malformed responses.
- Duplicate requests, retries, and idempotency.
- Batch or scheduled workloads if the service has them.

For each case, save inputs and expected behavior. Avoid time-sensitive data unless pinning `Clock`, random seeds, or dataset snapshots.

Reset databases, broker topics, caches, and filesystem fixtures to an identical state before each mode, or use isolated namespaces per run. Running all three modes back-to-back on data mutated by earlier requests can cause functional diffs stemming from test state rather than the runtime.

### 4.3. Compare Responses and Side Effects

Do not check HTTP status alone. Compare:

| Component | How to verify |
| --- | --- |
| Status code | Must be equivalent for the same request. |
| JSON body | Compare structure/values after normalizing nondeterministic fields. |
| Headers | Check content type, caching, correlation, and security headers. |
| Database | Compare row state, transaction outcomes, and constraint behavior. |
| Messages | Compare payload, key, headers, and emitted message count. |
| Cache | Check key/value/TTL and post-warm-up results. |
| Errors | Same business error types and public error contract. |
| Security | Same authorization decisions without leaking sensitive data. |

You may ignore truly nondeterministic fields like per-run request IDs or timestamps, provided you still validate their format, validity, and semantics. Never normalize fields that clients or downstream consumers depend on.

### 4.4. Differential Testing Across All Three Modes

Using the same test corpus, run sequentially against:

1. The JAR on standard JVM.
2. The same JAR running with `spring.aot.enabled=true`.
3. The native executable.

Capture responses and side effects from each mode and compare them against expected output or an approved baseline.

~~~mermaid
flowchart TD
    A[Canonical test corpus] --> B[Standard JVM]
    A --> C[JVM + Spring AOT]
    A --> D[Native Image]
    B --> E[Capture responses and side effects]
    C --> E
    D --> E
    E --> F[Normalize nondeterministic fields]
    F --> G[Compare with contract]
    G --> H{All modes pass?}
    H -->|No| I[Investigate functional divergence]
    H -->|Yes| J[Open performance benchmark gate]
~~~

### 4.5. Test Areas Prone to Divergence in Native Image

Focus extra attention on areas likely to differ between JVM and Native Image:

- Reflection and dynamic class loading.
- Resource loading from classpath or filesystem.
- Serialization and polymorphic binding.
- Dynamic proxies and framework-generated classes.
- JNI, native libraries, and cryptography providers.
- Timezone, locale, charset, and filesystem assumptions.
- Class initialization and static state.
- `ServiceLoader` and provider discovery.
- Configuration read at build time vs. runtime.

Spring Boot recommends continuing to run most unit/integration tests on the JVM, then focusing native tests on areas prone to divergence. [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html).

## 5. Organize Tests in Tiers

| Tier | Standard JVM | JVM AOT | Native |
| --- | --- | --- | --- |
| Unit tests | Run full suite | Reusable if tests do not depend on dynamic context | Select tests verifying native runtime |
| Spring integration tests | Run full suite | Run with AOT assets/context | Can use Native Build Tools native tests |
| Contract/API tests | Run same corpus | Run same corpus | Run same corpus |
| Database/broker integration | Same container/service | Same container/service | Same container/service |
| Executable smoke test | JAR startup/ready | AOT JAR startup/ready | Native startup/ready |
| End-to-end tests | Run over HTTP | Run over HTTP | Run over HTTP |
| Performance tests | JVM baseline | JVM AOT baseline | Native executable |

Native tests take longer because the test image itself must be compiled. Native tests can run on a CI schedule or at release stages, while JVM tests remain the fast feedback loop for most changes. Spring Boot and Native Build Tools provide `nativeTest` for Maven/Gradle per their respective configurations.

~~~bash
./mvnw -PnativeTest test
~~~

~~~bash
./gradlew nativeTest
~~~

Profile/task names depend on plugin version and build configuration. [Spring Boot — Native Image Testing](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html).

## 6. Distinguish Startup, Cold Request, and Steady State

Do not collapse everything into a single "startup time" number.

### 6.1. Process Startup

Measure from process/container creation until the process starts serving the health endpoint. Use the exact same readiness definition across all three modes.

Spring Boot Actuator exposes two useful metrics:

- `application.started.time`: time taken for the application to start.
- `application.ready.time`: time from launch until the application is ready to accept requests.

Also measure externally via a supervisor/load harness so results do not depend on how each runtime records metrics. [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).

### 6.2. Cold First Request

After readiness, send the first request to representative endpoints. The first request can trigger:

- Lazy initialization.
- Connection pool acquisition.
- TLS handshakes or DNS lookups.
- Cache misses and deserialization.
- JIT compilation in the JVM.
- Data loading or client initialization.

Record first-request latency separately. Do not substitute `application.ready.time` for first-request latency.

### 6.3. Warm-Up and Steady State

Standard JVM requires warm-up for the JIT to identify hot methods and optimize code. JVM running Spring AOT shares this behavior because it still runs on the JVM.

Native Image has no HotSpot JIT warm-up, yet the service still needs warm-up for connection pools, caches, DNS/TLS, lazy data, and downstream clients. Therefore:

1. Wait for readiness.
2. Execute the identical warm-up request sequence.
3. Exclude the warm-up window from steady-state results.
4. Run the measurement workload for a fixed duration.
5. Record latency and throughput as a time series to spot drift.

If the goal is cold-start/serverless, do not exclude first requests from results. If the goal is long-running services, report cold-start and steady-state metrics as two separate groups.



## 7. Designing Benchmarks for a Spring Boot Service

### 7.1. Prefer HTTP-Level Benchmarks

For a Spring Boot service, use the same external load generator to send requests to all three modes. Tools like `k6`, Gatling, or `wrk` can generate load outside the process.

Example:

~~~bash
k6 run --duration 10m --vus 40 orders-workload.js
~~~

Or for a simple endpoint:

~~~bash
wrk -t4 -c40 -d10m http://localhost:8080/api/orders
~~~

The workload must specify:

- Request mix by endpoint.
- Payloads and dataset.
- Authentication.
- Concurrency or offered RPS.
- Client think time and retry behavior.
- Warm-up and measurement durations.
- Stop conditions if the service breaches SLOs.

Do not use a simple `/health` endpoint to represent business workloads when production handles databases, serialization, caching, and downstream calls.

### 7.2. Two Load Models to Measure

**Fixed concurrency:** hold the number of concurrent clients constant to observe how many requests the system processes and how latency shifts.

**Fixed offered load:** hold the request arrival rate constant to compare latency/errors at identical traffic demand.

These two measurements answer different questions. When a service saturates, fixed-concurrency can mask rising latency by reducing throughput; fixed-offered-load exposes queueing backlog, timeouts, and errors when the system cannot keep up with traffic.

### 7.3. Use JMH in the Right Scope

[JMH](https://github.com/openjdk/jmh) is a harness for nano/micro/milli benchmarks targeting the JVM. Use JMH to analyze methods or algorithms on standard JVM and JVM AOT when benchmarking code paths isolated from container/application startup.

Never take a JMH microbenchmark score and compare it directly against a `k6`/HTTP run of Native Image. Those are two different measurement levels. For service-level comparisons, use the same external HTTP harness across all three modes. If microbenchmarking native code, build an equivalent native harness and verify it measures the same operations, inputs, and semantics.

### 7.4. Avoid Flawed Benchmarks

- Do not run benchmarks inside an IDE or on a machine with fluctuating background load.
- Do not run all three variants simultaneously on the same CPU/memory if they contend for resources.
- Do not alter request mixes across modes.
- Do not rely on a single run.
- Do not skip JIT warm-up if targeting JVM steady state.
- Do not skip cache/connection warm-up for a Native Image service.
- Do not benchmark instrumented/debug executables instead of production builds.
- Do not let the load generator become the bottleneck.
- Do not compare runs when downstream databases/brokers experience uneven background load.

JMH also recommends properly configured benchmark projects with warm-up/forking and peer review; a harness cannot eliminate flawed benchmark design on its own. [OpenJDK JMH README](https://github.com/openjdk/jmh).

## 8. Controlling the Benchmark Environment

### 8.1. Keep Hardware and Platform Equivalent

Record and fix:

- CPU model, core count, and instruction set.
- RAM and memory bandwidth.
- OS/kernel and architecture.
- libc and container base image.
- CPU quota and CPU pinning if used.
- Memory limit and swap policy.
- Filesystem/storage and network path.
- JDK/GraalVM distribution and version.

Native executables are compiled for a target platform. If the baseline runs on Linux x64 while native runs on ARM64, the benchmark compares both runtime and hardware.

### 8.2. Keep Resource Limits Identical

When deploying in containers, use identical:

- CPU quota/request.
- Memory limit/request.
- Swap policy.
- Replica count.
- Network namespace and port path.
- Container logging and sidecars.
- Readiness/health behavior.

Never run the JVM unrestricted on the host and compare it against a native container capped at 512 MiB. Every conclusion must rest on an identical resource envelope.

### 8.3. Control Downstream Dependencies

Databases, caches, brokers, and external APIs can dominate latency more than the Java runtime. Keep identical:

- Database snapshot/schema/indexes.
- Connection pool limits.
- Dataset and initial cache state.
- Broker topics/partitions and consumer configuration.
- External service latency or test doubles with fixed distributions.
- Timeout/retry/circuit-breaker settings.

If downstream systems have background load, measure dependency latency separately and re-run as needed. One mode must never inherit a warm connection pool while another mode has to initialize a fresh pool.

## 9. Metrics to Record Across All Three Modes

| Category | Metrics | Purpose |
| --- | --- | --- |
| Startup | Process start-to-ready, `application.started.time`, `application.ready.time` | Measure readiness time. |
| First request | First-request p50/p95/p99 | Spot lazy initialization and cold-path costs. |
| Throughput | Requests/second or messages/second | Measure processing capacity. |
| Latency | p50, p95, p99, and max | Measure response time and tail latency. |
| Reliability | Error rate, timeouts, retries, rejected requests | Check quality under load. |
| CPU | Average/peak CPU, throttling | Measure processing cost and saturation. |
| Memory | RSS/PSS, cgroup current/peak, heap when available | Compare process/container footprint. |
| GC | Count, total time, pause distribution when available | Understand allocation/collection pressure. |
| JVM | JIT compilation time, class loading, and thread metrics | Understand JVM-mode-specific overhead. |
| Build | Build duration, executable/JAR size | Evaluate pipeline and artifact cost. |
| Operations | Restarts, OOMs, readiness failures | Check operational stability. |

Do not require every runtime to emit the exact same internal metrics. For example, JIT compilation time only makes sense on the JVM; Native Image has no HotSpot JIT. Compare directly using shared metrics like startup-to-ready, throughput, latency, CPU, and RSS/cgroup; use runtime-specific metrics to explain root causes.

### 9.1. Spring Boot Actuator

Useful meters include:

- `application.started.time` and `application.ready.time`.
- `http.server.requests`.
- `jvm.memory.*`, buffer pool, GC, and thread metrics in JVM modes.
- `process.*` and `system.*` where supported by binders/runtime.
- `jdbc.connections.*` and `hikaricp.*`.
- `http.client.requests` if using instrumented builders.

Meter names and availability depend on version, registry, and runtime. In Native Image, do not assume every JVM meter carries the exact same semantics as HotSpot. Combine OS process/cgroup metrics with Actuator metrics. [Spring Boot Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).

### 9.2. Measure Memory Consistently

Use OS RSS/PSS and cgroup current/peak across all three modes. JVM heap used is not equivalent to the RSS of a native executable. Likewise, do not compare executable file size to resident memory.

Record:

- Process RSS/peak RSS.
- PSS if multiple processes share pages.
- cgroup `memory.current`, `memory.peak`, `memory.max`.
- Heap used/committed/max in JVM modes.
- GC and buffer metrics if exposed by the runtime.

Include sidecar/helper processes if they share the same cgroup. Clearly report metric sources and units.

## 10. Analyzing Results by Workload

### 10.1. Cold-Start-Sensitive Workloads

If the application scales to zero, runs as a serverless function, or spawns new processes frequently, focus on:

- Process start-to-ready.
- First-request latency.
- Memory after startup.
- Image/container pull time.
- New replica creation time.

Native Image can offer major advantages here, but factor in image pull time, scheduling, and dependency readiness if those affect production targets.

### 10.2. Long-Running Workloads

For services running many hours/days, measure:

- Warm steady-state throughput.
- p95/p99 latency under target load.
- CPU per request.
- Memory plateau and peak.
- GC frequency/time.
- Behavior during bursts and soak runs.

The JVM often achieves high performance after JIT warm-up. JVM AOT can speed up Spring context startup while retaining JIT. Native Image can have a smaller footprint, while throughput depends on workload and optimization flags. Never use startup results to infer steady-state throughput.

### 10.3. Memory-Constrained Workloads

When running under tight container limits, compare:

- Peak cgroup memory.
- RSS after warm-up and at peak load.
- GC pressure.
- OOMs/restarts.
- Throughput and latency under the same limit.

A mode using less memory while dropping throughput or inflating tail latency may not be the best fit for that service.

### 10.4. CPU-Bound vs. I/O-Bound Workloads

CPU-bound workloads expose compiler/runtime efficiency. I/O-bound workloads can be dominated by databases, networking, serialization, and connection pools.

Separate at least:

- CPU-bound operations.
- Database/API-heavy requests.
- Serialization/payload-heavy requests.
- Mixed production traffic.

When modes show no difference in an I/O-bound test, do not conclude the runtimes are equivalent in CPU efficiency. Conversely, small CPU microbenchmarks do not represent end-to-end latency.

## 11. Statistical Rigor and Reporting

### 11.1. Independent Repetitions

Each mode requires multiple independent runs, each starting a fresh process. Interleave execution order to reduce effects from background load, thermal throttling, or CPU frequency shifts.

Report:

- Median startup and latency.
- p95/p99 request latency.
- Mean/median throughput across runs.
- Min/max or confidence intervals where statistically appropriate.
- Peak memory per run and variance across runs.

Never cherry-pick the best run. If variance is high, increase run count or stabilize the environment before drawing conclusions.

### 11.2. Separate Warm-Up and Measurement

A single run should follow clear phases:

1. Start a fresh process.
2. Wait for readiness.
3. Send warm-up traffic using a fixed script.
4. Begin the measurement window.
5. Maintain load for the full duration.
6. Stop the process and archive metrics/logs.
7. Wait for resources to drain before the next run.

For cold-start benchmarks, skip warm-up and measure process start and first request separately. Never mix cold-start and steady-state numbers into one average.

### 11.3. Use Shared SLOs and Performance Gates

Performance gates should align with service requirements, for example:

- p99 latency stays within SLO.
- Error rate does not exceed defined thresholds.
- Throughput meets target traffic.
- Peak memory retains headroom below the container limit.
- Startup-to-ready meets scale-up timing.
- CPU does not throttle at the target operating point.

Do not enforce a fixed percentage improvement threshold across all modules. Weigh effect size alongside variance and operational impact.

## 12. Standard Results Table

Use one table per release and per target platform:

| Metric | Standard JVM | JVM + Spring AOT | Native Image |
| --- | ---: | ---: | ---: |
| Source commit | Record commit | Record commit | Record commit |
| JDK/GraalVM | Record version | Record version | Record version |
| Build mode | JVM | AOT JAR | Native executable |
| Startup-to-ready median | Record value | Record value | Record value |
| First request p95 | Record value | Record value | Record value |
| Throughput at target load | Record value | Record value | Record value |
| p95/p99 latency | Record value | Record value | Record value |
| Error/timeout rate | Record value | Record value | Record value |
| CPU average/peak | Record value | Record value | Record value |
| RSS/cgroup peak | Record value | Record value | Record value |
| Heap/GC metrics | Record if available | Record if available | Record if exposed |
| Artifact size | JAR size | AOT JAR size | Executable/image size |
| Build duration | Record value | Record value | Record value |
| Functional parity | PASS/FAIL | PASS/FAIL | PASS/FAIL |

Do not leave metrics blank without explanation. If a metric is meaningless in a mode, record N/A and explain why; if unavailable due to missing instrumentation, explicitly mark it unmeasured.

## 13. Maintaining Baselines Across Upgrades

### 13.1. Pin the Toolchain

Every baseline must record:

- Spring Boot and Spring Framework.
- JDK/GraalVM distribution and version.
- Native Build Tools plugin.
- Maven/Gradle wrapper.
- OS/architecture/libc.
- Container base image.
- GC, heap options, march, PGO, and build arguments.
- Runtime flags and environment configuration.

When upgrading, avoid changing all components simultaneously if your goal is isolating regression sources. Upgrade one intentional group at a time, then re-run parity and performance suites.

### 13.2. When Must AOT/Native Artifacts Be Rebuilt?

Rebuild AOT assets and Native Image whenever changing:

- Source code or bean configuration.
- Spring Boot/Spring Framework version.
- Dependency graph.
- Build-time profiles/conditions/environment.
- GraalVM/JDK or Native Build Tools.
- Reachability metadata or reflection/resource hints.
- OS/architecture/CPU target.
- Native build arguments, GC, or PGO profile.

Never use an old native executable to represent new source. Never reuse stale AOT-generated classes after dependencies or bean configuration change.

### 13.3. Baselines and Regression History

Store each run with metadata:

- Git commit.
- Build logs and commands.
- Artifact checksums.
- Workload script/version.
- Dataset ID.
- Platform/resource limits.
- Raw time series and summary.
- Functional test report.
- Known deviations and decisions.

Compare the current release against both the approved baseline and the immediately preceding release. When major shifts occur, establish a new baseline while retaining history to explain trends.

## 14. Making Mode Selection Decisions

| Product priority | Mode to evaluate closely | Rationale |
| --- | --- | --- |
| Scale-to-zero/cold start | Native Image | Startup and initial memory footprint are typically critical. |
| Fast startup while needing JVM ecosystem | JVM + Spring AOT | Uses generated Spring initialization code while keeping JVM/JIT. |
| Long-term throughput | Standard JVM and JVM AOT | JIT can optimize for the workload over long runs. |
| Low container memory | Native Image and JVM with tuned heap budget | Compare peak RSS/cgroup under identical limits. |
| High runtime flexibility | Standard JVM | Keeps classpath/bean/configuration decisions at runtime. |
| Native deployment/no JRE | Native Image | Executable has no JVM dependency and targets a specific platform. |
| Incremental transition needed | JVM AOT first, Native later | Validates Spring AOT generated code before native compilation. |

No single mode is optimal for every service. Choose based on SLOs, traffic patterns, build cost, platform, compatibility, and team operational readiness.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling JVM AOT "native" | Mistakenly assumes JVM AOT lacks JIT. | Clarify it is Spring AOT code running on the JVM. |
| Comparing different commits/dependencies | Unclear where differences originate. | Use the exact same source revision and dependency lock. |
| Using different AOT profiles | Bean sets diverge across modes. | Record build-time profiles/conditions and share AOT assets. |
| Running startup benchmarks only | Ignores steady-state throughput/latency. | Measure cold start and warm steady state separately. |
| Skipping JVM warm-up | Underestimates post-JIT performance. | Use fixed warm-up and report cold start separately. |
| Skipping Native Image service warm-up | Cache/connection startup skews numbers. | Run the same warm-up sequence across all modes. |
| Comparing heap to RSS | Compares two different memory scopes. | Use RSS/cgroup for all; add heap metrics as diagnostic context. |
| Comparing JMH scores to HTTP load tests | Two non-equivalent measurement levels. | Use the same external harness for service-level comparisons. |
| Using health endpoint as sole workload | Fails to represent business logic. | Use realistic request mixes and payloads. |
| Ignoring downstream systems | Database/network can mask runtime effects. | Pin or separately measure dependency latency. |
| Reporting average latency only | Hides tail latency. | Report p50/p95/p99 and error rates. |
| Benchmarking only once | Easily skewed by background noise. | Run independent repetitions and report variance. |
| Omitting build provenance | Cannot reproduce baselines later. | Store toolchain, commands, artifact checksums, and workload versions. |

## 16. Hands-on Exercise: Building a Three-Mode Baseline for Orders Service

**Context:** An Orders Service currently runs on a standard JVM. The team wants to see whether Spring AOT reduces startup and whether Native Image reduces memory while still meeting throughput/p99 latency targets.

### Tasks

1. Select a Git commit and lock the dependency graph.
2. Record Spring Boot, JDK/GraalVM, Maven/Gradle, and Native Build Tools versions.
3. Identify profiles, feature flags, and properties affecting bean conditions.
4. Build an AOT-generated JAR.
5. Run the JAR on standard JVM.
6. Run the same JAR with `spring.aot.enabled=true`.
7. Build the Native Image from the same AOT output.
8. Run the identical functional test corpus across all three modes.
9. Compare responses, database state, message outputs, and error behavior.
10. Open the performance gate only once all three modes achieve functional parity.
11. Run cold-start tests with fresh processes/containers.
12. Run warm-up and steady-state tests using the same k6/Gatling/wrk workload.
13. Collect startup-to-ready, first-request latency, RPS, p95/p99, errors, CPU, RSS, and cgroup peak.
14. Repeat multiple times in interleaved order.
15. Populate the results table and evaluate against SLOs.
16. Archive raw data, artifact checksums, workload scripts, and baseline metadata.
17. Upgrade Spring Boot or GraalVM on a dedicated branch and repeat the workflow.
18. Classify any regression as functional behavior, Spring AOT, Native Image compatibility, or runtime performance.

### Evidence Dossier

| Evidence | Contents to archive |
| --- | --- |
| Source | Git commit and dependency lock/BOM. |
| Toolchain | JDK/GraalVM, Spring Boot, Maven/Gradle, and plugin versions. |
| AOT environment | Build profiles, feature flags, and properties used during `processAot`. |
| Artifacts | Standard JAR, AOT JAR, native executable, and checksums. |
| Functional parity | Test corpus, response diffs, DB/message side effects, and outcome. |
| Workload | Script, request mix, dataset, concurrency, and duration. |
| Environment | CPU, RAM, OS, architecture, container limits, and downstreams. |
| Startup | Process start, readiness, and first request. |
| Performance | Throughput, p50/p95/p99, errors, CPU, and memory. |
| Decision | Selected mode, SLOs met, regressions, and known limitations. |

### Completion Criteria

- [ ] Accurately explain standard JVM, JVM AOT, and Native Image modes.
- [ ] Build all three artifacts/modes from the same source and dependency graph.
- [ ] Control build-time evaluated profiles/conditions.
- [ ] Pass functional parity tests prior to benchmarking.
- [ ] Produce cold-start, first-request, and steady-state results.
- [ ] Use identical workloads and resource limits.
- [ ] Report throughput, tail latency, error rate, CPU, and RSS/cgroup.
- [ ] Do not substitute JMH results for service-level load tests.
- [ ] Perform multiple independent runs and report variance.
- [ ] Store provenance to reproduce baselines after upgrades.
- [ ] Reach a mode selection decision grounded in SLOs and operational cost.

## 17. Self-Check Questions

1. How does JVM AOT in Spring Boot differ from Native Image in terms of runtime engine?
2. Why does JVM AOT still have JIT warm-up?
3. What part of application startup does `spring.aot.enabled=true` change?
4. Why can `@Profile` and `@ConditionalOnProperty` be constrained when using AOT?
5. How do you produce all three modes from the same AOT-generated assets?
6. What must functional parity compare beyond HTTP status?
7. Why should reflection, serialization, resources, and dynamic proxies be tested on Native Image?
8. How does startup-to-ready differ from first-request latency?
9. Why does the JVM need warm-up, and why does a Native Image service still need warm-up?
10. Why shouldn't JMH scores be compared directly against HTTP load tests?
11. Which metrics can be compared directly across all three modes?
12. Why can't heap used replace RSS/cgroup memory?
13. When upgrading Spring Boot/GraalVM, which artifacts must be rebuilt?
14. How do you decide among JVM, JVM AOT, and Native Image based on SLOs?

## 18. Official Documentation

Commands and plugin DSLs depend on Spring Boot, JDK/GraalVM, and Native Build Tools versions. Check documentation for your project's exact versions:

- [Spring Boot — Ahead-of-Time Processing With the JVM](https://docs.spring.io/spring-boot/reference/packaging/aot.html): running AOT-generated initialization code on the JVM with `spring.aot.enabled`.
- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): differences between JVM deployment, Spring AOT, and Native Image.
- [Spring Boot — Maven AOT Plugin](https://docs.spring.io/spring-boot/maven-plugin/aot.html): `process-aot`, `native` profile, and Maven build integration.
- [Spring Boot — Gradle AOT Plugin](https://docs.spring.io/spring-boot/gradle-plugin/aot.html): `org.springframework.boot.aot`, `processAot`, and `nativeCompile`.
- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html): testing AOT on the JVM and native tests.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): startup, JVM, process, and HTTP metrics.
- [GraalVM Native Image — Optimizations and Performance](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/): optimization levels, GC, PGO, and CPU targets.
- [GraalVM Native Image — Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/): build resource usage, executable output, and recommendations.
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh): structuring JVM microbenchmarks and measurement caveats.

**Key takeaway:** JVM AOT is Spring AOT-generated initialization code running on the JVM, so it still uses JIT. Native Image is an AOT-compiled executable with its own closed-world constraints. Verify functional parity first, then benchmark both cold start and steady state with identical source, configuration, workload, and resource limits; archive provenance so comparisons remain valid across every upgrade.

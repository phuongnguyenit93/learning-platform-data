# PGO: Collecting Representative Profiles and Recompiling on Supported Platforms

## 1. Why Does Native Image Need Profiles?

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring Boot applications are processed with **Spring AOT** and compiled into a **GraalVM Native Image** to evaluate startup time, memory, throughput, and operability. Native Image compiles Ahead-of-Time (AOT): the compiler analyzes reachable code and emits machine code before the application runs. Unlike a JIT compiler, an AOT compiler cannot observe production workloads on its own to see which methods are called frequently, which conditional branches dominate, or which data types appear most often.

**Profile-Guided Optimization (PGO)** feeds runtime behavioral data into AOT compilation. The team builds an instrumented executable, runs that executable under a representative workload to collect a profile, and passes that profile into the next native build. The compiler gains data to optimize hot methods, branches, call sites, and common execution paths.

For a Spring Boot service, a profile can help the compiler prioritize frequent request paths such as authentication, queries, JSON serialization, business calculations, and internal service calls. If the collected workload diverges sharply from production, the profile can steer the compiler toward rarely used paths and degrade performance.

After this lesson, learners will be able to:

1. Explain how PGO supplies runtime data to the AOT compiler.
2. Distinguish PGO profiles from reachability metadata produced by the tracing agent.
3. Verify whether a GraalVM distribution, version, OS, and architecture support PGO.
4. Build an instrumented native executable with `--pgo-instrument`.
5. Run a representative workload and capture `.iprof` files with `-XX:ProfilesDumpFile`.
6. Collect multiple profiles, merge them, or pass multiple files to the compiler.
7. Build an optimized executable with `--pgo=<profile>`.
8. Configure Maven/Gradle Native Build Tools for each stage.
9. Evaluate profile quality, performance, and the impact of stale profiles.
10. Establish a reproducible CI workflow on the exact deployment platform.

> **Important prerequisite:** PGO is unavailable in GraalVM Community Edition. You must use a GraalVM distribution and version that support PGO, and verify that the Native Image target and native toolchain match the deployment platform.

## 2. What Does PGO Record?

A profile summarizes program behavior at runtime. Depending on the data Native Image collects, the compiler can learn:

- Which methods are called frequently and their relative call counts.
- Which conditional branches are usually true or false.
- Which call sites predominantly receive a specific data type.
- Which allocation paths occur most frequently.
- Which execution contexts appear most often.

For example, an order-processing endpoint may receive 95% valid requests and 5% rejected requests. If a representative profile captures that distribution, the compiler has evidence to prioritize the valid-order path. If the profile contains only error requests, the compiler may spend optimization effort on error paths rarely hit in production.

### 2.1. How PGO Differs from Tracing Agent

These two profile/metadata artifacts serve different purposes:

| Tool | Collects | Purpose |
| --- | --- | --- |
| Native Image Tracing Agent | Reflection, resources, proxies, serialization, and JNI accesses observed on the JVM. | Generates reachability metadata so Native Image knows which dynamic accesses to retain. |
| PGO instrumentation | Method frequencies, branches, types, and runtime behavior used by the compiler for optimization. | Guides the AOT compiler to optimize code for the workload. |

PGO does not automatically register reflection, resources, or proxies. If a native build fails due to missing reachability metadata, resolve the corresponding hints/metadata; PGO does not replace that step.

### 2.2. Does PGO Guarantee Better Speed?

No. PGO gives the compiler data to make better decisions for workloads resembling the profile. Results still depend on code, workload, GraalVM version, CPU, GC, build configuration, and measurement methodology.

PGO is commonly used to improve throughput or hot-path performance. Executable size can also change as the compiler separates hot code from cold code. Startup, memory, and latency do not automatically improve in every application; measure each target metric separately.

## 3. Checking Supported GraalVM and Platforms

Before generating a profile, verify the build environment:

~~~bash
java -version
native-image --version
native-image --help
native-image --print-options
~~~

Check:

- Whether the distribution includes PGO support.
- Whether the GraalVM version accepts `--pgo-instrument`, `--pgo`, and required runtime options.
- Whether the JDK version is compatible with Spring Boot, Spring Framework, and the dependency graph.
- Whether Native Image supports the executable's target OS/architecture.
- Whether the C compiler, linker, libc, headers, and native libraries match the target.
- Whether the CI runner or build container uses the exact verified toolchain.

Current GraalVM documentation explicitly states that PGO is unavailable in GraalVM Community Edition. If an option is unrecognized, do not rename it based on an old article; verify the distribution and version first.

### 3.1. Profile Collection Platform vs. Build Platform

PGO profiles can often be collected on one platform and used to build an executable on another. However, some classes/methods are OS- or architecture-specific, such as POSIX vs. Windows implementations. A profile collected on one platform may lack entries for code existing only on another platform.

Best practices:

- Collect profiles on the same OS/architecture as the target optimized executable whenever possible.
- If using a cross-platform profile, inspect the build report and benchmark on the real target.
- For multiple targets such as Linux x64 and Linux ARM64, consider maintaining separate profiles per target.
- Do not assume a profile from an arbitrary GraalVM release or dependency graph remains optimal for the current release.

A PGO profile is compiler input data, not a cross-platform executable. The final native binary must still be built for a target supported by GraalVM and the native toolchain.

### 3.2. When Cross-Compilation Is Needed

Native Image offers `--target=<OS>-<architecture>` on supported versions. Cross-compilation also depends on the target toolchain, C libraries, and native dependencies; adding `--target` alone does not guarantee the build environment is ready.

For multi-platform pipelines, prefer building on runners/containers matching each target. When cross-compiling, verify the exact-release GraalVM documentation, target C compiler, linker, libc, and all native libraries before releasing.

### 3.3. CPU Architecture and `-march`

`-march` controls the CPU instruction set the compiler may emit. `-march=native` can improve performance when the binary runs solely on machines sharing the same CPU features, yet can prevent the executable from running on other nodes in a cluster.

When deploying across heterogeneous machines, pick a compatible CPU baseline or build separately per CPU group. Keep `-march` identical when comparing baseline and PGO so results are not skewed by two different instruction sets.

## 4. Overall PGO Workflow

PGO for Native Image involves three main runs:

~~~mermaid
flowchart TD
    A[Spring Boot source and dependency graph] --> B[Build instrumented native executable]
    B --> C[Run representative workload]
    C --> D[Profile .iprof written on process exit]
    D --> E[Review, store, or merge profiles]
    E --> F[Build optimized executable with --pgo]
    F --> G[Check build output and target]
    G --> H[Benchmark same workload against baseline]
    H --> I{Meets performance goals and regression checks?}
    I -->|No| J[Adjust workload/profile/build options]
    J --> B
    I -->|Yes| K[Package and release optimized executable]
~~~

Three stages to distinguish:

1. **Instrumented build:** inserts counters into AOT code to record profiles.
2. **Profile collection:** runs the instrumented executable under a representative workload.
3. **Optimized build:** recompiles the source using the collected profile.

The instrumented executable exists solely for profile collection. It carries overhead and is not a production binary.

## 5. Creating a Non-PGO Baseline

Before optimizing, build a standard native executable from the same source and application configuration. Example with a Spring Boot executable JAR:

~~~bash
native-image \
  -jar target/orders-service.jar \
  -o orders-default
~~~

If the project uses Native Build Tools, run native compilation with the existing Maven/Gradle configuration. Record:

- Source commit and dependency graph.
- Spring Boot, JDK, GraalVM, and plugin versions.
- OS/architecture, libc, CPU features, and native toolchain.
- Build arguments, GC, heap options, and `-march`.
- Build duration, executable size, and build report.
- Startup-to-ready, throughput, latency, CPU, and memory under the standard workload.

The baseline establishes whether PGO makes a measurable difference. If throughput is the goal, use a workload long enough to measure steady state. If the application targets serverless/cold start, measure startup and request completion separately.

### 5.1. Adding a Same-Optimization-Level Baseline When Needed

On Oracle GraalVM, PGO builds typically default to optimization level `-O3`, whereas normal builds may default to `-O2`. To isolate the effect of the profile from the effect of the optimization level, also measure a non-PGO executable built with `-O3` if your version supports it.

You can maintain three variants:

| Variant | Purpose |
| --- | --- |
| Default native | Measures current production configuration. |
| Non-PGO native with same `-O3` | Isolates the impact of optimization level. |
| PGO native | Measures actual gain from the profile. |

Do not simultaneously change GC, `-march`, heap size, build flags, and workload when trying to isolate PGO's specific benefit.

## 6. Building the Instrumented Executable

Use `--pgo-instrument` so the compiler emits a binary with profile-collection counters:

~~~bash
native-image \
  --pgo-instrument \
  -jar target/orders-service.jar \
  -o orders-instrumented
~~~

For Spring Boot, replace the illustrative command with your project's actual classpath/launcher and build arguments when the native plugin manages compilation. The goal is producing the same application and native configuration with only PGO instrumentation added.

### 6.1. Instrumented Builds Have Overhead

Instrumentation increases execution time and can raise memory/CPU usage. Instrumented builds can also consume extra compiler resources. Therefore:

- Do not use an instrumented executable to benchmark production performance.
- Do not compare instrumented binary latency against the baseline.
- Provision sufficient CPU/RAM for the `native-image` builder.
- Keep all other build arguments identical to the baseline.
- Never ship an instrumented executable as a production binary.

If the `native-image` builder hits `OutOfMemoryError`, check build logs, memory limits, parallelism, and builder heap. You may need more build resources or fewer threads; this is build-process memory, distinct from service runtime memory.

## 7. Running a Workload to Collect a Profile

### 7.1. Where and When Is the Profile Written?

By default, an instrumented executable writes the profile to `default.iprof` in the working directory when the process exits. You can specify a custom path with the runtime option:

`-XX:ProfilesDumpFile=<path>`

Example:

~~~bash
mkdir -p profiles

./orders-instrumented \
  -XX:ProfilesDumpFile=profiles/steady-state.iprof \
  --spring.profiles.active=performance
~~~

This option must be passed to the native executable at runtime. Ensure the directory exists and the process has write permission. In containers, mount a writable volume for the profiles directory or write to a suitable filesystem and copy the artifact out.

Profiles are normally dumped during application shutdown. For long-running services, shut the process down gracefully so the runtime has a chance to write the profile. If the process receives `SIGKILL`, the container gets OOM-killed, or the machine halts abruptly, the profile may be incomplete.

### 7.2. Workload for a Spring Boot Service

GraalVM does not generate HTTP workloads for web applications automatically. Use a load-testing tool or end-to-end test with a request mix close to production.

Example launching the instrumented service:

~~~bash
./orders-instrumented \
  -XX:ProfilesDumpFile=profiles/orders-steady.iprof \
  --spring.profiles.active=performance
~~~

From another process, run the load test:

~~~bash
k6 run --duration 5m --vus 40 pgo-workload.js
~~~

`pgo-workload.js` should hit real endpoints used by the service with payloads, authentication, and request ratios matching production. Once the load test finishes, stop the service using your environment's graceful shutdown mechanism, then verify the profile file.

For simple GET endpoints, `wrk` can be used:

~~~bash
wrk -t4 -c32 -d5m http://localhost:8080/api/catalog
~~~

A single health endpoint usually does not represent business workloads. Target endpoints exercising real business logic, serialization, database/cache operations, and downstream calls.

### 7.3. Designing a Representative Workload

A good workload should reflect:

- Request proportions across endpoints or use cases.
- Ratios of successful requests, validation failures, and business rejections.
- Payload sizes, data types, and value distributions.
- Concurrent users/requests and request rate.
- Cache hit/miss ratios and database queries.
- Realistic authentication, authorization, and serialization.
- Feature flags/profiles enabled in deployment.
- Sufficient duration for the service to traverse startup, warm-up, and steady state.

Do not force every rare error case into the profile at equal frequency. The profile should mirror relative production frequencies. Rare cases must still be tested for correctness; they do not need to become hot paths.

### 7.4. Warm-Up Before Profile Capture

For services with connection pools, caches, lazy initialization, or TLS clients, you can separate warm-up from the main profiling phase:

1. Start the instrumented executable.
2. Wait for readiness and dependency initialization.
3. Send warm-up requests following a consistent procedure.
4. Run the profile workload with the defined request mix.
5. Shut down the process gracefully to write the profile.

Do not omit critical initialization paths if your application goals cover startup/cold paths. Decide explicitly whether the profile should represent steady state or include startup, then design the workload accordingly.

### 7.5. Why Unit Tests Usually Make Poor Profiles

Unit tests aim to exercise many corner cases, not reproduce production frequencies. A test suite might call an error helper hundreds of times and hit the primary business path only a few times; such a profile can mislead the compiler into prioritizing the wrong code.

Prefer:

- End-to-end tests representing production flows.
- Benchmarks with request/data distributions close to production.
- Workload replay from safely sanitized data.
- Load tests weighted by request ratios measured in production.

Unit tests may be used only if they genuinely represent the workload you want to optimize, but never use an entire unit-test suite as a default profile.

## 8. Collecting Multiple Profiles for Multiple Scenarios

A single profile may not sufficiently represent an application with distinct workloads. You can run the instrumented executable multiple times with separate filenames.

Example profile for a read path:

~~~bash
./orders-instrumented \
  -XX:ProfilesDumpFile=profiles/read-heavy.iprof \
  --spring.profiles.active=performance
~~~

After the process exits, run the instrumented executable again with a write workload:

~~~bash
./orders-instrumented \
  -XX:ProfilesDumpFile=profiles/write-heavy.iprof \
  --spring.profiles.active=performance
~~~

Create a dedicated batch profile if batch processing is an important production workload:

~~~bash
./orders-instrumented \
  -XX:ProfilesDumpFile=profiles/batch.iprof \
  --spring.profiles.active=batch-performance
~~~

Profiles must be collected from the same instrumented application version and documented scenarios. Never let multiple processes write concurrently to the same profile filename; assign a distinct file per process.

### 8.1. Passing Multiple Profiles Directly to the Compiler

The `--pgo` option accepts a comma-separated list of files:

~~~bash
native-image \
  --pgo=profiles/read-heavy.iprof,profiles/write-heavy.iprof,profiles/batch.iprof \
  -jar target/orders-service.jar \
  -o orders-pgo
~~~

GraalVM reads all specified profiles. You do not put `.iprof` files on the application classpath or package them into the runtime image; they are build inputs.

### 8.2. Merging Profiles with Native Image Utils

To produce a single combined profile managed as one artifact, Native Image Utils provides `merge-pgo-profiles`.

~~~bash
native-image-utils merge-pgo-profiles \
  --input-file=profiles/read-heavy.iprof \
  --input-file=profiles/write-heavy.iprof \
  --input-file=profiles/batch.iprof \
  --output-file=profiles/orders-combined.iprof
~~~

You can also pass a directory as the source:

~~~bash
native-image-utils merge-pgo-profiles \
  --input-dir=profiles/ \
  --output-file=profiles/orders-combined.iprof
~~~

The merge command produces a profile containing the union of types, methods, and profile entries from the input files. Because a merged profile can span multiple scenarios, retain the list of source files and workload proportions used to generate each one.

### 8.3. Accounting for Traffic Distribution When Combining Profiles

Having a set of profiles does not by itself guarantee the resulting mix matches production. If a read workload accounts for 90% of traffic while a batch job runs once daily, workload execution should reflect that relative weight.

Design collection durations/frequencies in proportion to real traffic or run a single composite workload with a clearly defined distribution. Do not run every scenario for the same duration and assume the combined profile matches production ratios.

## 9. Compiling the Optimized Executable with PGO

Once you have the profile, rebuild the same application passing the profile to the compiler:

~~~bash
native-image \
  --pgo=profiles/orders-combined.iprof \
  -jar target/orders-service.jar \
  -o orders-pgo
~~~

If using the default `default.iprof` in the working directory, some versions may pick it up automatically when running a build without specifying a path. In production pipelines, always pass an explicit path to avoid accidentally picking up a stale profile or a file in the wrong directory.

### 9.1. Which Profile Should You Use?

Select a profile created from:

- The exact application and dependency graph close to the target release.
- A workload verified for representativeness.
- A compatible GraalVM version.
- The matching platform/architecture whenever possible.
- Documented scenarios that remain valid for the current code.

If a profile comes from an earlier release, check how much hot paths and key dependencies changed. A stale profile may still be readable by the compiler, yet no longer be beneficial.

### 9.2. Do Not Mix Instrumentation and Optimization in the Same Build

The two stages use distinct options:

| Stage | Build Argument | Result |
| --- | --- | --- |
| Instrumented | `--pgo-instrument` | Executable writes a profile on exit. |
| Optimized | `--pgo=profiles/orders-combined.iprof` | Executable optimized using the profile. |
| Baseline | No PGO option | Standard native executable for comparison. |

Select only the matching configuration for each build. Never leave `--pgo-instrument` enabled in the final production build.

## 10. Configuring Maven Native Build Tools

With Maven, add build arguments to the `native-maven-plugin` configuration. Example for an instrumented profile:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--pgo-instrument</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

When building the profile-collection executable, activate the Maven profile containing that argument:

~~~bash
./mvnw -Pinstrumented -Pnative package
~~~

For the optimized build, use a separate Maven profile with the argument:

~~~xml
<buildArg>--pgo=profiles/orders-combined.iprof</buildArg>
~~~

Run the optimized build using the configured profile:

~~~bash
./mvnw -Ppgo-optimized -Pnative package
~~~

These are illustrative snippets. Merge them into your existing POM while preserving plugin version, executions, main class, Spring AOT configuration, and other build arguments. Never activate both instrumented and optimized profiles together if doing so passes both options into one `native-image` invocation.

If using `spring-boot-maven-plugin` or Buildpacks to build the executable, check how that plugin/builder accepts native build arguments in your exact version. Do not assume every default Spring Boot `native` profile has PGO enabled.

## 11. Configuring Gradle Native Build Tools

With Kotlin DSL, add `--pgo-instrument` to the native binary when creating an instrumented executable:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--pgo-instrument")
        }
    }
}
~~~

When switching to the optimized build, substitute the collected profile:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--pgo=profiles/orders-combined.iprof")
        }
    }
}
~~~

With Groovy DSL:

~~~groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add('--pgo=profiles/orders-combined.iprof')
        }
    }
}
~~~

Run the plugin's native compile task:

~~~bash
./gradlew nativeCompile
~~~

To produce the instrumented binary, use the build configuration with `--pgo-instrument`; to produce the optimized binary, use the build configuration with `--pgo=...`. You can split these into Gradle properties or a convention plugin so CI selects explicitly.

DSL syntax and task names depend on Native Build Tools and Spring Boot Gradle Plugin versions. Inspect `./gradlew tasks`, the plugin DSL reference, and project build logs. Avoid copying a Gradle snippet from another release without confirming the property exists.

## 12. Verifying the Compiler Actually Used the Profile

Do not rely solely on exit code 0. Read the **Builder configuration** section in Native Image build output.

On Oracle GraalVM, the compiler configuration line can show PGO status, for example:

- `off`: PGO not used.
- `instrument`: binary instrumented for profile collection.
- `user-provided`: compiler used a user-supplied profile.
- `ML-inferred`: profile inferred by a machine learning model in certain configurations/releases.

For an instrumented build, verify status is `instrument`. For an optimized build using `.iprof`, verify status is `user-provided` or the corresponding indicator for your GraalVM version.

If build output reports `off`, check:
- Whether the build argument reached the `native-image` process.
- Whether the profile path matches the working directory.
- Whether the Maven/Gradle profile was activated.
- Whether you are running a GraalVM distribution that supports PGO.
- Whether any warning or message noted the profile was ignored.

GraalVM provides `native-image --native-image-info` and build reports to record toolchain/configuration. Archive logs from both instrumented and optimized builds as evidence.

## 13. Evaluating Profile Quality

### 13.1. Profile Applicability and Profile Relevance

Some GraalVM versions can print two metrics:

- **Profile applicability:** degree to which code locations needing profile data have corresponding entries.
- **Profile relevance:** degree to which profile entries correspond to code in the built application.

You can instruct the compiler to print these metrics with:

~~~bash
native-image \
  --pgo=profiles/orders-combined.iprof \
  -H:+PGOPrintProfileQuality \
  -jar target/orders-service.jar \
  -o orders-pgo
~~~

`-H:+PGOPrintProfileQuality` is an experimental option in current documentation. Use it only when supported by your GraalVM version, and do not treat absolute figures as the sole quality score. Their best use is tracking trends when reusing a profile across builds or comparing different profiles.

### 13.2. Checking for Stale Profiles

A profile can be reused across minor code changes, yet a skewed profile can degrade performance below a non-PGO build. Re-evaluate when:

- Algorithms or hot paths change.
- Request mix or workload ratios shift.
- A dependency upgrade affects frequently invoked code.
- Features, serializers, database access, or downstream clients are added/removed.
- Profiles/runtime configurations change.
- GraalVM/JDK is upgraded or the target platform changes.
- The profile no longer reflects production behavior.

You do not need to re-collect profiles after documentation edits or refactors affecting only cold code. However, maintain a policy to re-profile periodically or whenever hot paths change.

### 13.3. Profile Metadata Must Include Provenance

Store alongside the `.iprof` file:

| Field | Content |
| --- | --- |
| Application commit | Commit that built the instrumented executable. |
| GraalVM | Distribution, version, and JDK. |
| Target | OS, architecture, libc, and CPU baseline. |
| Dependencies | Dependency graph/BOM version. |
| Workload | Script, request mix, dataset, and duration. |
| Environment | Profiles, feature flags, and runtime configuration. |
| Collected at | Collection timestamp. |
| Source profiles | Input files if the profile was merged. |
| Owner | Pipeline/team responsible for the profile. |

A profile is a build input, not a runtime asset of the service. Store it in a versioned artifact repository or CI artifact store with metadata; never place it inside the application's `resources` directory by mistake.

## 14. Benchmarking Baseline vs. PGO Optimized

### 14.1. Never Benchmark the Instrumented Binary

An instrumented executable carries overhead from counters and instrumentation. It can be noticeably slower than a normal binary. Use it strictly for profile collection, never for reporting production performance.

Benchmark two binaries:
- Non-PGO native baseline.
- PGO-optimized native binary.

To isolate the impact of `-O3`, include a non-PGO baseline at the same optimization level. Keep all other settings identical.

### 14.2. Fix Measurement Conditions

Use identical:

- Machine/CPU or identical runner type.
- OS, architecture, libc, and container base image.
- CPU quota, memory limit, and swap policy.
- Dataset, request payloads, and traffic distribution.
- Concurrency, duration, warm-up, and iteration count.
- Spring profiles, environment variables, and downstream services.
- Logging, metrics, tracing, and GC configuration.
- JDK/GraalVM version and non-PGO build arguments.

Never compare a PGO binary running on a newer CPU against a baseline on an older CPU. If build targets differ, results may reflect platform differences rather than PGO.

### 14.3. Metrics to Record

| Metric | Objective |
| --- | --- |
| Throughput/RPS | Requests processed per second at the same concurrency. |
| p50/p95/p99 latency | Response time distribution. |
| CPU utilization | CPU cost to process the same workload. |
| Allocation/GC | Allocation pressure and GC time if exposed by the runtime. |
| RSS/peak memory | Executable footprint under load. |
| Startup-to-ready | Time from process start to readiness. |
| Executable size | Final binary size. |
| Build duration | Cost to build baseline, instrumented, and optimized binaries. |

PGO typically targets hot code and throughput. If p99 latency or startup is the primary goal, verify them directly; do not infer from throughput that every latency percentile dropped.

### 14.4. Repeat and Analyze

Run multiple iterations and record median, min/max, or spread. Alternate baseline/PGO run order to reduce background load or CPU frequency drift effects. Use the exact same workload script and preserve raw measurements.

If PGO shows no improvement:
- Confirm the profile was actually used.
- Check whether the workload is representative.
- Check whether the profile is stale or too short.
- Compare `-O` and `-march`.
- Inspect profile quality/build report if the options are available.
- Re-measure after changing one factor at a time.

If PGO worsens results, test building without PGO and collect a fresh profile. Never keep PGO merely because the pipeline spent time generating a profile.

## 15. Organizing PGO in CI/CD

You can split the pipeline into jobs:

~~~mermaid
flowchart TD
    A[Checkout source and resolve dependencies] --> B[Build instrumented native executable]
    B --> C[Start instrumented service]
    C --> D[Replay representative workload]
    D --> E[Graceful shutdown and collect iprof]
    E --> F[Upload profile artifact with provenance]
    F --> G[Build optimized native executable]
    G --> H[Verify PGO status and build report]
    H --> I[Run correctness tests]
    I --> J[Benchmark baseline and PGO]
    J --> K{Passes performance gate?}
    K -->|No| L[Keep baseline and investigate profile]
    K -->|Yes| M[Package and publish optimized artifact]
~~~

### 15.1. Separate Artifacts by Purpose

Keep distinct:
- Instrumented executable.
- `.iprof` profile files.
- Merged profile if applicable.
- PGO-optimized native executable.
- Baseline executable.
- Build logs/reports and benchmark results.

Never accidentally ship the instrumented executable in a release. Do not copy the profile into the runtime container if the service does not need it at runtime.

### 15.2. Profile Refresh Policy

Profiles can be re-collected:
- Every major release.
- Whenever hot paths or request distributions change.
- On a schedule, such as nightly/weekly depending on application change rate.
- From a versioned benchmark workload.
- From a dedicated instance/canary if an operational process accepts instrumentation overhead.

Do not reuse a profile indefinitely. Stale profiles can still be parsed by the compiler while steering optimization poorly. Tie each profile to its commit, dependency graph, workload, and target to decide when regeneration is needed.

### 15.3. Pre-Release Checks

- The native executable is a fresh optimized build.
- Build output confirms `user-provided` PGO.
- GraalVM distribution/version and target match requirements.
- Correctness tests pass.
- Benchmarks compare under identical workloads.
- No significant regression in latency, memory, or executable size.
- Profile provenance and build logs are archived.
- No instrumented executable is included in the release image.

## 16. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `--pgo-instrument` is unrecognized | GraalVM Community Edition or unsupported version. | Verify distribution/version and `native-image --help`. |
| Missing `default.iprof` | Process did not shut down, was killed, lacks write permissions, or wrong working directory. | Use `-XX:ProfilesDumpFile` with a writable path and graceful shutdown. |
| Empty/invalid `.iprof` file | Workload never ran, process halted abruptly, or profile failed to dump. | Check logs, runtime duration, and file after shutdown. |
| Optimized build reports PGO `off` | Build argument not passed or plugin profile not activated. | Check Maven/Gradle profile and Builder configuration. |
| Build fails to read profile | Wrong path, invalid profile output, or corrupted file. | Use the genuine `.iprof` artifact, never edit manually, re-collect profile. |
| PGO gives no gain | Unrepresentative workload, short profile, I/O-bound app, or unchanged hot paths. | Measure CPU-bound paths, expand workload coverage, and compare across runs. |
| PGO makes app slower | Skewed or stale profile, traffic mix differs from production. | Collect a fresh profile or revert to the non-PGO baseline. |
| Some methods lack profile entries | Code never executed or platform-specific code absent on collection OS. | Add scenarios or collect profile on the target platform. |
| Instrumented build hits OOM | Instrumentation increases build resource needs. | Increase builder RAM, tune `-J-Xmx` and `--parallelism`. |
| Profile works on one OS but lacks entries on another | Platform-specific implementation/JDK code differs. | Collect target-specific profiles or validate on target. |
| CI picks up an old profile by mistake | Artifact store lacks commit/workload tags or default file was reused. | Use versioned paths, provenance, and a refresh policy. |

### 16.1. Isolation Sequence

~~~mermaid
flowchart TD
    A[PGO build or runtime issue] --> B{Instrumented build succeeded?}
    B -->|No| C[Check GraalVM edition, version, target, and toolchain]
    B -->|Yes| D{Profile file created?}
    D -->|No| E[Check workload, write permissions, and graceful shutdown]
    D -->|Yes| F{Optimized build confirms PGO?}
    F -->|No| G[Check --pgo path and plugin arguments]
    F -->|Yes| H{Benchmark improved?}
    H -->|No| I[Evaluate profile quality and workload distribution]
    H -->|Yes| J[Run correctness tests and release checks]
    C --> A
    E --> A
    G --> A
    I --> A
~~~

## 17. Hands-On Exercise: Collecting a PGO Profile for a Spring Boot Service

**Scenario:** An order management service has three primary workloads: catalog lookup, order creation, and batch reconciliation. The team wants higher throughput for the Linux x64 native executable and wants to test whether profiling improves latency under heavy load.

### Tasks

1. Verify the GraalVM distribution supports PGO; record JDK, GraalVM, Native Build Tools, and native toolchain versions.
2. Lock in target OS/architecture, libc, CPU baseline, and container runtime.
3. Build a non-PGO native baseline; save the executable, build report, and benchmark results.
4. Build an instrumented executable with `--pgo-instrument`.
5. Create a workload script reflecting production catalog/create/reconciliation ratios.
6. Launch the instrumented service with `-XX:ProfilesDumpFile` pointing to a writable directory.
7. Wait for readiness, run warm-up, then run the profile workload for sufficient duration.
8. Shut down the service gracefully and verify the `.iprof` file was written.
9. Collect an additional profile for the batch scenario or another workload in a separate file.
10. Merge profiles via `native-image-utils merge-pgo-profiles` or pass the comma-separated list to `--pgo`.
11. Build the optimized native executable on a supported target.
12. Inspect build output to confirm the PGO profile was used.
13. Run correctness tests, native integration tests, and container smoke tests.
14. Benchmark baseline vs. optimized under identical request mix, CPU/memory limits, and iteration counts.
15. Record throughput, p95/p99 latency, CPU, RSS, startup, executable size, and build duration.
16. Decide whether to keep PGO, re-collect a profile, or revert to the baseline based on results.

### Results Record

| Evidence | Details to Save |
| --- | --- |
| Toolchain | GraalVM distribution/version, JDK, Native Build Tools, and C compiler. |
| Target | OS, architecture, libc, CPU baseline, and container image. |
| Baseline | Build arguments, output path, size, and benchmarks. |
| Instrumented build | Command, logs, and executable path. |
| Workload | Script, request mix, payloads, concurrency, duration, and dataset. |
| Profile | `.iprof` path, size, timestamp, and process shutdown outcome. |
| Profile sources | Input scenarios/profiles and merge details. |
| Optimized build | `--pgo` arguments, build log, and PGO status. |
| Benchmark | Throughput, p50/p95/p99, CPU, memory, and iteration count. |
| Decision | Results, regressions, profile freshness, and next action. |

### Completion Criteria

- [ ] Verified PGO availability on the GraalVM distribution/version.
- [ ] Selected a supported target OS/architecture and native toolchain.
- [ ] Built both baseline and instrumented native executables.
- [ ] Collected profiles from a representative workload rather than blindly running the entire unit-test suite.
- [ ] `.iprof` file written cleanly after graceful shutdown.
- [ ] Practiced collecting and merging multiple profiles.
- [ ] Optimized build uses `--pgo` and build output confirms PGO.
- [ ] Instrumented executable is not shipped.
- [ ] Benchmarked baseline vs. PGO under identical conditions and workload.
- [ ] Saved provenance to reproduce both profiles and optimized builds.

## 18. Self-Check Questions

1. What additional information does PGO provide to the AOT compiler?
2. How does a PGO profile differ from reachability metadata generated by the tracing agent?
3. Why is PGO unavailable in GraalVM Community Edition according to current documentation?
4. What characteristics does an executable built with `--pgo-instrument` have?
5. What is `-XX:ProfilesDumpFile` used for, and when is the profile normally written?
6. Why is an instrumented executable unsuitable for benchmarking production performance?
7. Why can a workload consisting of the full unit-test suite mislead compiler optimizations?
8. When should you collect multiple profiles, and when should you merge them?
9. Why can cross-platform profiles often work while collecting on the target platform remains best practice?
10. What effect can a stale profile have once hot paths change?
11. What status must build output show to confirm PGO was applied?
12. Which metrics besides throughput must be measured when comparing baseline and PGO?

## 19. Official Documentation

PGO options and support scope depend on GraalVM distribution, release, and target platform. Verify against your exact version before configuring:

- [GraalVM Native Image — Profile-Guided Optimization](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/PGO/): PGO principles, profile events, and profile collection.
- [GraalVM Native Image — Basic Usage of PGO](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/PGO/basic-usage/): instrumented builds, `ProfilesDumpFile`, `.iprof`, and optimized rebuilds.
- [GraalVM Native Image — PGO Frequently Asked Questions](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/PGO/faq/): representative workloads, unit tests, instrumentation overhead, and cross-platform profiles.
- [GraalVM Native Image — Tracking Profile Quality](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/PGO/profile-quality/): stale profiles, refresh schedules, applicability, and relevance.
- [GraalVM Native Image — Merging Profiles from Multiple Sources](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/PGO/merging-profiles/): `native-image-utils merge-pgo-profiles`.
- [GraalVM Native Image — Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/): PGO status, optimization level, build report, and build artifacts.
- [GraalVM Native Image — Command-line Options](https://www.graalvm.org/latest/reference-manual/native-image/overview/Options/): `--pgo`, `--pgo-instrument`, `--pgo-sampling`, `--target`, and option availability by version.
- [GraalVM Support](https://www.graalvm.org/latest/support/): distributions, certified platforms, and current support scope.

**Key takeaway:** PGO is only beneficial when the profile accurately describes the workload you want to optimize. Use a PGO-capable GraalVM distribution, build an instrumented executable, run a representative workload on the appropriate platform, store profiles with provenance, rebuild with `--pgo`, and benchmark the optimized binary under identical conditions against the baseline.

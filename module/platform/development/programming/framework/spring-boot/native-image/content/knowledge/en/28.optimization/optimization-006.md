# Garbage Collectors and Available Options by Distribution and Version

## 1. Why Choose a Garbage Collector for Native Image?

A garbage collector (GC) reclaims memory from Java objects that are no longer in use. When moving Spring Boot from the JVM to GraalVM Native Image, the application still needs to manage heap, allocations, object lifetimes, and memory pressure. However, Native Image GC choices, characteristics, and limits depend on the GraalVM distribution, version, operating system, and target architecture.

Do not assume a native executable always uses the same GC as the HotSpot JVM, or that every GC in the JDK exists in Native Image. Supported options can differ across GraalVM Community, Oracle GraalVM, commercial distributions, and releases. A build argument valid on one machine may be rejected by another toolchain.

In the **SPRING_BOOT_NATIVE_IMAGE** module, this lesson focuses on identifying available GCs, understanding common choices such as Serial and G1, recognizing Epsilon where supported by the distribution, configuring heap limits, and measuring workloads before choosing. The goal is to select a GC based on latency, throughput, footprint, and container limits rather than by collector name or defaults from another environment.

## 2. How Does Native Image GC Differ from HotSpot GC?

Native Image builds the executable ahead of time. The executable's runtime still includes memory management and GC, but it is not the full HotSpot JVM runtime. Certain collectors, diagnostic options, and HotSpot tuning flags may be unsupported or behave differently.

Distinguish between:

- **Build-time options:** GC selection and runtime configuration baked into the executable when the Native Image is created.
- **Runtime options:** heap bounds or parameters passed at launch, where supported by the runtime.
- **HotSpot flags:** JVM-specific options such as certain `-XX` collector-specific flags; they do not apply by default to a native executable.
- **Container limits:** CPU/RAM caps enforced by Docker/Kubernetes/cgroups, independent of the GC yet directly affecting allocation and collection behavior.

For example, `UseG1GC` is the familiar way to pick G1 on HotSpot. With Native Image, GC selection is typically done via a Native Image option such as `--gc=...` if that collector is supported by the distribution. Consult the `--help` output and documentation of your actual `native-image` compiler.

## 3. Identify Distribution and Version Before Configuring

Before choosing a GC, record the toolchain:

    native-image --version
    java -version
    native-image --help

If using a GraalVM distribution with its own commands or package manager, verify which `native-image` executable the build plugin actually invokes. On CI, multiple JDK/GraalVM installations may coexist; `java` and `native-image` do not necessarily come from the same distribution if `PATH` is misconfigured.

Record:

- Distribution/vendor and edition.
- GraalVM version/build number.
- JDK version.
- Installed Native Image component.
- OS and target architecture.
- Native Build Tools version.
- Spring Boot version.
- GC options listed by the compiler or confirmed in release documentation.

Never simply record "GraalVM latest". When comparing GCs or reproducing builds, the exact version is part of the result.

## 4. Common Collectors and Support Scope

Native Image has common GC choices, though the available list varies by distribution and release:

| Collector | General Characteristics | What to Verify |
|---|---|---|
| Serial GC | Simple collector, typically low footprint; suited to small workloads or low contention | Usually the default in many Native Image distributions |
| G1 GC | Region-based collector aiming to balance throughput and pause times on larger heaps | May depend on edition/distribution and version |
| Epsilon GC | No-op GC that never reclaims objects; suited only to processes with tightly bounded lifetimes/heaps | May be experimental or absent in a distribution; not for standard production GCs |

This table is a guide, not a support guarantee across all GraalVM releases. Some distributions provide only Serial; G1 may appear only in specific editions/versions; Epsilon may be absent or discouraged. Always check vendor docs and `native-image --help` on the exact toolchain used to build.

## 5. Serial GC

Serial GC is a straightforward collector, typically suited to applications with small-to-medium heaps, limited threads/CPUs, or tight footprint requirements. It can reduce management overhead compared to more complex collectors, though collection cycles can cause noticeable pauses when the heap is large or allocation pressure is high.

For a native Spring Boot service, Serial GC can be a reasonable starting point when:

- The workload does not allocate excessively many objects per second.
- Allocated core count is low.
- Heap size and live set are modest.
- Footprint and simplicity take priority.
- Latency targets are unaffected by measured pauses.

Do not assume Serial is always faster or uses less RAM in every scenario. Allocation rate, object graph, thread count, and live set determine the outcome.

In many Native Image distributions, Serial is the default. Even so, record the selected GC explicitly in build reports/logs rather than relying on assumptions.

## 6. G1 GC

G1 partitions the heap into regions and collects region by region, aiming to balance throughput and pause times for larger heaps. On Native Image, G1 is available only in certain distributions/editions/versions. Having G1 in GraalVM Community or a JDK does not automatically mean Native Image G1 is available.

If supported by the compiler, it can be selected with an option like:

    native-image --gc=G1 -o orders-service ...

Exact syntax and values must be confirmed in the release's help/documentation. If the compiler reports the GC is unsupported, do not try passing HotSpot flags as a workaround.

G1 may be worth testing when:

- The heap or live set is large.
- Many threads allocate objects concurrently.
- Throughput and pause times need balancing.
- Serial GC causes pauses/latency exceeding targets in benchmarks.

G1 can add overhead or memory footprint. Compare it against Serial under identical workloads and resource limits.

## 7. Epsilon GC and Special Cases

Epsilon is a no-op garbage collector: it allocates memory without reclaiming objects. Once the heap fills up, the process can fail instead of collecting to free memory. Consequently, it fits only special scenarios such as short-lived processes with strictly bounded allocations and a sufficiently sized heap with a well-defined process lifecycle.

Never use Epsilon for long-running Spring Boot web services or workloads with unbounded allocation. A request burst, growing cache, or unexpected object retention can exhaust the heap.

If a Native Image distribution includes Epsilon, treat it as a specialized choice for controlled measurement/testing use cases. Verify the option and support status in release docs; do not assume `--gc=epsilon` is accepted in every version.

## 8. Selecting GC via Native Image Build Argument

Native Image typically uses the `--gc` option to choose a collector when supported:

    native-image --gc=serial -o orders-service ...

Or if the toolchain supports G1:

    native-image --gc=G1 -o orders-service ...

Value casing may be case-sensitive depending on the CLI/version. Copy the exact value from official help and toolchain documentation. If the option is omitted, the compiler uses the distribution/version default.

Do not mix HotSpot GC selection syntax (`-XX:+UseG1GC`) with Native Image options. Some runtime flags may be supported in native executables, but use them only when explicitly confirmed by Native Image documentation.

## 9. Passing the GC Option via Gradle

With the GraalVM Native Build Tools Gradle plugin, build arguments are typically set on the binary:

    graalvmNative {
        binaries {
            main {
                buildArgs.add('--gc=serial')
            }
        }
    }

To test G1 when supported by the distribution:

    graalvmNative {
        binaries {
            main {
                buildArgs.add('--gc=G1')
            }
        }
    }

These are configuration examples; check exact DSL and plugin version for your project. Verify the native task uses the right binary configuration and logs show the argument. If multiple binaries exist (`main`/`test`), configure the exact target being measured.

Do not pass multiple conflicting GC selections in the same build. Each benchmark build should specify one collector clearly so results remain comparable.

## 10. Passing the GC Option via Maven

With the Native Maven Plugin, build arguments can be declared in plugin configuration:

    <plugin>
        <groupId>org.graalvm.buildtools</groupId>
        <artifactId>native-maven-plugin</artifactId>
        <configuration>
            <buildArgs>
                <buildArg>--gc=serial</buildArg>
            </buildArgs>
        </configuration>
    </plugin>

This is an illustrative example. Confirm the project's actual plugin version, execution, and native profile. If using multiple Maven profiles for GC variants, ensure each profile outputs a distinct artifact and logs the selection clearly.

Do not edit the POM blindly from an example if your current plugin reads arguments via another setting. The goal is proving the compiler received the option, not just having a string in the build file.

## 11. Setting Heap Limits

The GC operates within the process's heap bounds. A native executable can accept supported runtime memory options such as `-Xms` and `-Xmx`, though support level and semantics must be verified for your Native Image version.

Run example:

    ./orders-service -Xms128m -Xmx512m

`-Xms` sets initial heap; `-Xmx` caps max heap according to runtime-supported semantics. Do not equate `-Xmx` with the container memory limit: RSS also covers native memory, thread stacks, code, mapped files, and off-heap regions.

If a container has a 512 MiB limit and max heap is also set to 512 MiB, the process can still OOM due to off-heap memory. Leave headroom and measure actual cgroup memory.

## 12. Distinguishing Heap, RSS, and Container Memory

These metrics are not interchangeable:

| Metric | Meaning |
|---|---|
| Java heap | Region managed for objects by the GC |
| Live set | Objects still referenced after collection |
| Allocation rate | Amount of objects/bytes allocated over time |
| RSS | Resident memory pages of the process |
| Container/cgroup memory | Memory accounted to the container/cgroup |
| Memory limit | Hard limit enforced by the runtime/orchestrator |

The GC primarily manages the heap. Shrinking the heap does not guarantee RSS drops proportionally; enlarging the heap can reduce collection frequency while raising the memory ceiling. Native Image also uses off-heap memory for code, metadata, threads, and native libraries.

When benchmarking, record both heap-related metrics (if available) and RSS/cgroup memory. Do not declare a GC optimal from a single `docker stats` reading at one point in time.

## 13. Understanding Live Set and Allocation Rate Before Switching GC

Two workloads with identical request rates can still exert very different GC pressure:

- Workload A allocates many short-lived objects with a small live set.
- Workload B allocates fewer objects yet retains a large cache/object graph.
- Workload C experiences allocation bursts during JSON parsing or PDF rendering.
- Workload D holds buffers/native resources longer than expected.

The GC must handle allocations and live objects, not just request counts. Before switching collectors, measure:

- Allocation rate over time.
- Live heap after collection.
- Collection frequency and pauses if provided by the runtime.
- Thread count and concurrency level.
- Object retention/caches.
- Peak memory during traffic bursts.

If the live set grows continuously, the issue may be a memory leak or unbounded cache rather than GC choice. Switching collectors cannot fix objects held forever by live references.

## 14. Choosing a GC by Workload and Goal

| Workload | Starting Direction | What to Measure |
|---|---|---|
| Small API, few cores, low heap | Serial if available | RSS, pauses, p95/p99 |
| High-concurrency API, large heap | Compare Serial and G1 if supported | Throughput, pauses, CPU, memory |
| Short-lived job, strictly bounded data/heap | Evaluate a lifecycle-appropriate GC; Epsilon only in special bounded cases | Peak heap, OOM, job duration |
| Long-running service, large cache | Supported collector suited to heap; monitor retention | Live set, pauses, RSS over time |
| Very tight container memory | Serial is usually a worthwhile baseline | Headroom, OOM, tail latency |

These are starting points, not rigid rules. A suitable collector must meet SLOs and memory limits under representative load.

## 15. Verifying the GC Option Is Actually Used

After configuring, verify step by step:

1. Check `native-image --version` and `--help` of the exact compiler.
2. Run the build with the chosen GC argument.
3. Confirm compiler logs do not ignore or reject the option.
4. Save the command line/build report if available.
5. Launch the executable and verify runtime behavior under workload.
6. Collect metrics/diagnostics supported by your distribution.
7. Record the GC selection in the benchmark report.

Do not rely solely on the POM/Gradle file. The build plugin might not apply settings to the task/binary you are invoking. If the compiler does not print the GC choice explicitly, check documentation and run observable tests.

## 16. Heap and GC Tuning Requires Container Headroom

Suppose a container has a 1 GiB memory limit. Never automatically set `-Xmx1g`, because the process still needs off-heap memory. Start with a lower heap limit, then measure peak cgroup memory under load.

Example Kubernetes runtime resource configuration:

    resources:
      requests:
        memory: "768Mi"
        cpu: "500m"
      limits:
        memory: "1Gi"
        cpu: "1"

This is an example resource budget, not a heap sizing recommendation. Choose `-Xmx` based on live set, allocation bursts, and native overhead. CPU limits also affect GC concurrency/throughput, especially when the collector uses worker threads.

If the process gets OOMKilled, check container events and cgroup metrics. Raising `-Xmx` while the container limit remains fixed can make things worse.

## 17. Benchmarking GCs Fairly

To compare Serial against G1 or another collector:

- Same source revision and dependencies.
- Same GraalVM distribution/version.
- Same CPU/RAM limits and container base image.
- Same heap bounds when the goal is comparing collectors; if heap differs, document it clearly.
- Same request mix, dataset, concurrency, and warmup policy.
- Same run count and measurement duration.
- Same observability overhead.
- Run each binary/collector in isolation without lingering old processes.

Measure at least:

| Metric | Purpose |
|---|---|
| Throughput | Overall processing capacity |
| p50/p95/p99 latency | User experience and tail latency |
| GC pause/frequency | Collection impact |
| CPU usage | Collector overhead |
| Peak heap/live set | Heap pressure |
| RSS/cgroup peak | Real memory footprint |
| OOM/restarts | Stability |
| Startup/readiness | Startup cost |

Run multiple iterations and report medians/distributions. A short benchmark can miss memory growth or long-horizon GC behavior.

## 18. Common Errors When Switching GCs

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Compiler rejects `--gc=G1` | Distribution/edition/version does not support it | Check support matrix and `--help` |
| `-XX:+UseG1GC` has no effect | Used a HotSpot flag unsuitable for Native Image | Use a documented Native Image option |
| RSS exceeds container limit while heap stays below `Xmx` | Native memory, stacks, code, or off-heap buffers | Measure cgroup usage and leave headroom |
| High Serial pauses | Large heap/live set or allocation pressure | Profile workload, try another collector if available |
| G1 uses more memory | Collector overhead/region structures | Compare total RSS and SLOs |
| Epsilon runs out of heap | Never reclaims objects | Do not use for long-running services; pick a collecting GC |
| OOM during traffic bursts | Insufficient heap limit or container limit | Measure bursts, right-size heap and memory budget |
| Heap grows continuously | Object retention/cache leak | Analyze object lifecycles, do not merely switch GCs |

## 19. Hands-On Exercise: Comparing Serial and Another Collector If Available

**Scenario:** A native Order API runs in a 1 GiB container and must keep p99 latency under SLO while absorbing request bursts.

**Step 1 — Identify toolchain.** Record distribution, edition, version, JDK, and supported GCs.

**Step 2 — Build baseline.** Build the native executable with the default GC; save build logs, build time, and binary digest.

**Step 3 — Measure baseline.** Run the standard request mix/concurrency, capturing throughput, p95/p99, RSS, cgroup peak, heap metrics, and OOM/restarts.

**Step 4 — Build Serial variant.** If Serial is the default, note that explicitly; no need to create a redundant duplicate variant.

**Step 5 — Build G1 variant.** Perform only if the distribution/version confirms support; use the exact option and save build arguments.

**Step 6 — Hold conditions equal.** Keep CPU/memory limits, heap bounds, dataset, duration, and observability config identical.

**Step 7 — Compare results.** Evaluate SLOs, tail latency, CPU, RSS, peak heap, and stability under bursts.

**Step 8 — Choose configuration.** Select the collector meeting SLOs with reasonable total resources; document version and support boundaries so future builds stay reproducible.

Completion criteria: the GC option is verified on the exact distribution; benchmarks share equivalent conditions; results cover latency/throughput/memory and failures; the decision does not rest solely on startup or a single run.

## 20. Conclusion

GraalVM Native Image garbage collectors must be chosen per specific distribution and version. Serial is usually a simple baseline; G1 can suit larger heaps/workloads if your edition supports it; Epsilon is strictly for special cases since it never reclaims objects. You cannot infer available collectors from HotSpot flags or a different GraalVM release.

Check `native-image --help`, pin your toolchain, distinguish build-time GC selection from runtime heap sizing, and measure heap, RSS, cgroup memory, pauses, throughput, and tail latency together. A sound GC configuration is one that meets SLOs inside the container's real memory budget with reproducible benchmark evidence.

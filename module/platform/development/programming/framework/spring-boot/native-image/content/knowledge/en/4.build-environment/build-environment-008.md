# Disk Space, RAM, and CPU for Native Compilation

Compiling a Spring Boot application into a **GraalVM Native Image** is a resource-intensive task at *build time*. Compared to producing a JAR file that runs on a JVM, Native Image must analyze call paths and reachable types (*reachability analysis*), process reflection/resource metadata, optimize code, compile to machine code, and link the executable. **Spring AOT** clarifies the Spring application's structure before GraalVM analyzes it, but it does not eliminate the cost of those phases.

Consequently, a Spring Boot service may run comfortably on a few hundred MB of RAM after startup yet **require multiple GB of RAM and several minutes of CPU processing to build the native binary**. This lesson guides you through estimating disk, RAM, and CPU resources, observing bottlenecks, and configuring Maven/Gradle or container builds so results are reproducible.

## 1. Distinguishing Build-Time Resources from Runtime Resources

| Aspect | Native Build | Running Native Executable |
|---|---|---|
| Goal | Analyze the entire reachable program and produce an executable | Start up and serve business workloads |
| CPU | Used for analysis, optimization, and machine code generation; can use multiple cores | Depends on requests, background tasks, and actual load |
| RAM | Needed for the builder, analysis structures, and auxiliary tools | Primarily for application/library heap and runtime |
| Disk | Needed for dependency caches, AOT code, intermediate files, executable, and container layers if any | Needed for executable, app data, logs, and workload storage |
| Tracked Metrics | Build time, peak RAM/RSS, CPU, free disk, build success rate | Startup time, RSS, throughput, latency, and stability |

**Do not infer the RAM required for the native compiler from the RAM used at native runtime.** The two phases perform entirely different work. Conversely, high RAM requirements in CI/CD do not prove the native application will use more RAM than the JVM in production.

High-level overview:

~~~mermaid
flowchart TD
    A["Spring Boot source and dependencies"] --> B["Spring AOT generates code and metadata"]
    B --> C["GraalVM Native Image: reachability and optimization"]
    C --> D["Machine code generation and executable linking"]
    D --> E["Native executable"]
    F["Build host CPU, RAM, and disk space"] --> B
    F --> C
    F --> D
    E --> G["Runs with its own runtime resources"]
~~~

In practice, phases may overlap or be implemented differently across tool versions; the diagram simply illustrates the sources of resource consumption.

## 2. Why Is Native Compilation Resource-Intensive?

A native build must process a large amount of information before an executable can run:

1. **Spring AOT** analyzes beans, auto-configuration, and AOT-capable components; generates Java sources and metadata.
2. **Reachability analysis** determines the methods, types, fields, and paths that must be included in the image.
3. **Code analysis and optimization** across reachable code, potentially including interprocedural and low-level optimization passes.
4. **Machine code generation** for the target architecture and operating system.
5. **Linking** against native runtime components and related libraries to produce the executable.
6. **Container packaging** if the pipeline also produces an image with Buildpacks or Docker.

Each step applies a different kind of pressure. Reachability and optimization can drive up RAM demand; code generation can keep many CPU cores continuously busy; linking and writing outputs increase disk demand. When building inside containers, cgroup/Docker limits and memory allocated to a VM or WSL also affect the outcome.

Complexity does not scale linearly with lines of application code. A small module that pulls in many libraries, reflection mechanisms, or annotation processors can have a much larger build time and footprint than expected.

## 3. Initial Machine Sizing Estimates

No single amount of RAM, CPU, or free disk space is **guaranteed to fit every application**. Values vary with JDK/GraalVM version, Spring Boot version, dependencies, metadata, optimization mode, operating system, and container build method. The table below is only a **practical starting baseline**, not an official minimum requirement or a guarantee that every project will build successfully.

| Reference Scale | Logical CPUs for Build | Available RAM for Build Environment | Free Disk Space to Reserve |
|---|---:|---:|---:|
| Demo API or small service, few dependencies | 4 cores | 8–16 GB | 15–25 GB |
| Medium Spring Boot service, several common starters | 8 cores | 16–32 GB | 25–50 GB |
| Large app, wide dependency graph, or parallel builds | 12–16+ cores | 32–64+ GB | 50+ GB, depending on caches and container layers |

These numbers represent **environment capacity to begin experimenting**. A simple project can build on lower specs; a complex project may need significantly more. Confirm using **actual observed peak resource usage** and leave headroom for future builds as dependencies grow.

If you only have an 8 GB RAM machine, test a small sample service, avoid running heavy apps concurrently, and consider building real projects on a CI runner/host with more RAM. If a machine has 16 GB yet runs an IDE, browser, Docker Desktop, and a database, **available RAM for the native build will be less than 16 GB**.

### Sizing by Workload Type

- **Learning and trial builds:** prioritize an environment with enough RAM to finish the build; adding CPU reduces duration when not bottlenecked by RAM or I/O.
- **Stable CI/CD:** measure the peak of a full build, add safety headroom, and govern how many jobs run concurrently.
- **Monorepo or multiple services:** budget resources according to the **number of concurrent builds**, not just a single service.
- **Container builds:** check Docker/WSL/VM quotas, Docker storage capacity, and runner configuration in addition to host specs.

## 4. RAM: Usually the First Constraint to Control

During a Maven/Gradle and Native Image build, RAM can be consumed by multiple processes or components:

- The JVM running Maven or Gradle, and the Gradle daemon if active.
- The JVM/process used by Native Image for analysis and compilation.
- Native off-heap memory: thread stacks, compiler structures, libraries, and memory-mapped files.
- The linker along with system tool processes.
- Operating system, IDE, Docker daemon/VM, and other services.

**The builder's Java heap is not the total RAM used by the build.** Setting a heap cap with `-J-Xmx` only caps one portion of the Native Image process's memory; total RSS and overall pipeline consumption can be higher.

### Example RAM Budget

Suppose a build machine has 16 GB of RAM and you plan to grant Native Image up to 8 GB of heap:

~~~text
Build machine RAM              : 16 GB
Native Image max heap          :  8 GB  (example)
Remaining memory               :  8 GB
Used by                        : OS, non-heap/native memory,
                                 Maven/Gradle, linker, Docker/WSL,
                                 daemons, other processes
~~~

This is an **illustrative allocation**, not a guaranteed formula. If Native Image needs a larger heap, capping `-J-Xmx8g` can cause `java.lang.OutOfMemoryError`. If the machine or container runs out of RAM for off-heap overhead, the OS may terminate the process before it even hits that heap cap.

Never set heap equal to 100% of physical RAM. In containers, budget based on the actual memory limit assigned to the container/VM and the processes running inside it.

### Distinguishing Two Memory-Exhaustion Failure Modes

| Symptom | Initial Interpretation | Action to Take |
|---|---|---|
| `java.lang.OutOfMemoryError: Java heap space` | Builder JVM heap is insufficient or analysis structures are too large | Check current heap setting; consider raising `-J-Xmx` if physical RAM allows |
| Build is `Killed`, exits with 137 on Linux/container, or logs `OOMKilled` | Likely terminated by OS/cgroup because total memory exceeded limit | Check cgroup/Docker/runner limits, reduce concurrency, or raise RAM limit |
| Machine swaps heavily and build crawls | Physical memory under severe pressure even before process dies | Close concurrent processes, limit concurrency, add RAM |
| Gradle daemon disappears | Could be RAM pressure or a daemon-specific failure | Check daemon logs and system logs; do not assume the bug is in Native Image |

Exit code 137 usually indicates the process received SIGKILL, yet **by itself is insufficient to conclude OOM**; inspect kernel logs or container status as well.

## 5. CPU: Core Count, Parallelism, and Real-World Gains

Native compilation has CPU-intensive phases that can utilize multiple cores. Consequently, scaling from 2 cores to 4 or 8 often shortens builds when RAM and I/O are sufficient. However, **adding cores does not always reduce build time linearly**.

Reasons include:

- Some phases are not fully parallelizable.
- More workers can increase RAM pressure, garbage collection, or I/O contention.
- VMs and CI runners may have CPU quotas or share resources with other jobs.
- The linker and sequential phases can become the bottleneck once compilation speeds up.

For example, if 8 cores shorten a build yet push peak RAM past the runner's limit, a stable 4-core configuration may be more effective for CI. Evaluate **successful build duration**, rather than aiming solely for 100% CPU utilization.

### Parallelism Across Three Levels

1. **Parallelism inside Native Image:** number of threads used by the build tool.
2. **Build tool parallelism:** Maven/Gradle can execute multiple tasks/modules or workers concurrently.
3. **CI parallelism:** multiple native build jobs sharing a runner or host.

Total CPU/RAM pressure is the combined result of all three levels. An 8-vCPU runner executing **two native jobs in parallel** is not equivalent to each job having 8 vCPUs exclusively.

## 6. Disk Space: More Than Just the Executable Size

Actual disk space required during a build can be vastly larger than the final native binary. Account for inputs, caches, and temporary data:

| Storage Location | What Typically Consumes Disk |
|---|---|
| Source workspace | Source code, resources, Spring AOT generated sources |
| `~/.m2/repository` | Downloaded Maven dependencies and plugins |
| `~/.gradle/caches` | Dependencies, Gradle distributions, and build caches |
| `target/` or `build/` | Classes, AOT code, intermediate objects/outputs, test artifacts, executable |
| OS/build temp directory | Intermediate files, logs, object/linker outputs depending on tool |
| Docker/Buildpacks storage | Builder image, run image, layers, buildpack caches, final image |

Do not estimate "the native executable is only 80 MB, so I need 80 MB of disk." Even a build producing a few-dozen-MB binary can use multiple GB for compiler intermediates and caches. When building with Buildpacks, Docker also needs space for images/layers and caches retained between builds.

### Where Free Disk Space Actually Matters

On machines with multiple drives or volumes, distinguish:

- **Workspace volume:** holds the project, `target/`, and `build/`.
- **Cache volume:** where Maven/Gradle stores dependencies and caches.
- **Temporary volume:** where the OS or linker writes temporary files.
- **Docker data volume:** where the Docker daemon stores layers and images; this may live inside a VM/WSL rather than on the same partition as your source code.

Plenty of free space on one drive will not help if the partition hosting Docker data or temp files fills up. Match a `No space left on device` error to the exact volume being written.

## 7. Checking Resources Before Building

Verify **how much CPU, RAM, and disk the build machine actually sees**, especially when working with Docker Desktop, WSL, or CI containers. Numbers shown on the host may differ from container quotas.

### On Linux

~~~bash
# Number of logical CPUs provided by the system
nproc

# Visible RAM/swap in the current environment
free -h

# Capacity and usage percentage of partitions
df -h

# Observe processes and CPU/RAM pressure during a build
top
~~~

Inside a container, these commands may reflect host info or differ from cgroup limits depending on the environment. Check container or runner memory/CPU settings as well.

### On Windows PowerShell

~~~powershell
# Total physical RAM and currently free RAM (in GB)
$os = Get-CimInstance Win32_OperatingSystem
[pscustomobject]@{
    TotalRAM_GB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
    FreeRAM_GB  = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
}

# Logical core count across processors on the machine
(Get-CimInstance Win32_Processor |
    Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum

# Free space on disk drives
Get-PSDrive -PSProvider FileSystem |
    Select-Object Name,
        @{Name='FreeGB'; Expression={[math]::Round($_.Free / 1GB, 1)}},
        @{Name='UsedGB'; Expression={[math]::Round($_.Used / 1GB, 1)}}
~~~

This information reflects the Windows host; when building inside WSL2 or Docker Desktop, check that environment's limits and disk space too.

### With Docker

~~~bash
docker info
docker system df
~~~

`docker info` checks the environment and resources reported by the daemon; `docker system df` shows storage consumed by Docker objects. During a container build, you can observe the container with `docker stats` while the corresponding container exists and is running.

**Do not automatically run commands that wipe all Docker caches/layers** simply because disk space is low; identify which data is safe to prune and the impact on other projects sharing the host.

## 8. Running a Native Build and Recording Metrics for Comparison

For a Spring Boot project configured with GraalVM and the corresponding plugin, common commands are:

~~~bash
# Maven: typically requires a configured native profile
./mvnw -Pnative native:compile

# Gradle: requires the GraalVM Native Build Tools plugin
./gradlew nativeCompile
~~~

On Windows, use the matching wrappers `mvnw.cmd` and `gradlew.bat`. Output paths and native profile/task configuration may vary by project.

### Timing on Linux

~~~bash
# Measure elapsed time and peak RSS if GNU time is installed
/usr/bin/time -v ./mvnw -Pnative native:compile
~~~

GNU `time -v` typically reports fields such as `Elapsed (wall clock) time`, `Maximum resident set size`, and CPU percentage. If the build spawns multiple processes, interpret reported numbers according to how `time` aggregates child processes; it is **not necessarily total host peak RAM**. Combine with host or cgroup monitoring tools for fuller measurements.

### Timing on PowerShell

~~~powershell
Measure-Command { .\mvnw.cmd -Pnative native:compile }
~~~

`Measure-Command` reports execution time but does not automatically report peak RAM/CPU. Monitor Task Manager, Resource Monitor, or an equivalent system monitor while the command runs.

### Minimum Resource Log

Each measurement run should record:

| Field | Illustrative Example |
|---|---|
| Artifact | `payment-api`, pinned commit and build config |
| Toolchain | Spring Boot version, JDK/GraalVM version, Maven/Gradle version |
| Host/runner | 8 vCPU, 16 GB RAM, Linux x86-64 |
| Build type | Local nativeCompile or Buildpacks container |
| Cache | Clean/cold or warm cache |
| Duration | Wall-clock elapsed time |
| Memory | Process peak RSS or job/cgroup peak memory |
| Disk | Free space before/after and peak if measurable |
| Result | Success/failure, failing stage, and relevant logs |

Values in this table illustrate how to record results, **not empirical measurements**. Clearly distinguish *cold builds* (no relevant caches present) from *warm builds* (dependency/layer caches populated), as build duration and I/O can differ substantially.

## 9. Tuning RAM and Parallelism

If measurements confirm Native Image is running out of heap, you can pass options to `native-image`. For example, setting a maximum heap of 8 GB and limiting compiler threads to 4; **apply only if your Native Image version supports these flags**:

~~~text
-J-Xmx8g
--parallelism=4
~~~

`-J-Xmx8g` sets the heap limit for the JVM running the Native Image tool. It **does not guarantee total RAM consumption stays within 8 GB** and does not make the resulting native application run with an 8 GB heap.

`--parallelism=4` limits the number of threads Native Image uses in supported versions. Check `native-image --help` or the documentation for your exact tool version to confirm syntax; some releases use different configuration mechanisms.

### Gradle Configuration Example (Groovy DSL)

When using the GraalVM Native Build Tools plugin, you can add to `build.gradle`:

~~~groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add('-J-Xmx8g')
            buildArgs.add('--parallelism=4')
        }
    }
}
~~~

### Maven Configuration Example

When the project enables `org.graalvm.buildtools:native-maven-plugin`, the plugin configuration can include:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-J-Xmx8g</buildArg>
            <buildArg>--parallelism=4</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

The snippets above illustrate only the build arguments portion; the project still needs proper plugin, dependency, and toolchain configuration. Do not copy 8 GB / 4 threads as a universal default. If builds frequently hit OOM, first check actual available RAM, container limits, and concurrent build count; setting a larger heap on a memory-starved machine can make matters worse.

## 10. When Building with Buildpacks or Docker

Spring Boot supports building container images; in certain setups, the Spring Boot Maven/Gradle plugin uses Cloud Native Buildpacks and a native-capable builder. This build path usually **consumes extra disk and can add RAM pressure** due to builder images, layers, caches, and container builds.

~~~bash
# Maven example with native profile and plugin configured
./mvnw -Pnative spring-boot:build-image

# Gradle example with corresponding native image/buildpacks configuration
./gradlew bootBuildImage
~~~

Gradle's `bootBuildImage` command does not automatically produce a native executable solely because GraalVM Native Build Tools is installed. You must configure the proper build image/native environment settings per your Spring Boot version and builder.

Check four factors:

1. **Is the Docker daemon running with enough disk space for images/layers?**
2. **Is the build container allocated enough RAM and CPU?** On Docker Desktop, VM/WSL limits can be lower than total host RAM.
3. **Does the builder match the target OS/architecture?** Native executables are platform-bound.
4. **Is there enough disk for both the builder cache and output image?** If CI uses ephemeral runners, data must be re-downloaded, affecting duration and disk usage.

**Avoid directly comparing local `nativeCompile` time against containerized `build-image` time** and blaming the difference entirely on the native compiler. The two pipelines have different dependency download, layering, and packaging costs.

## 11. Diagnosing Bottlenecks from Observable Signals

| Symptom | What to Investigate | How to Address |
|---|---|---|
| Build dies with `Java heap space` | Build heap too small for actual analysis | Inspect memory logs and heap setting; increase if host has headroom |
| Build killed abruptly in Docker/CI | cgroup/runner limit or memory pressure | Check OOM events, reduce concurrent jobs, raise memory limit |
| CPU stays high while build progresses | Compiler is actively using CPU; not necessarily a fault | Measure elapsed time and peak RAM before changing config |
| Low CPU, heavy disk activity, heavy swap | RAM or I/O bottleneck | Add RAM, reduce swap pressure, or move workspace/cache to faster disk |
| Build stops with `No space left on device` | Workspace, temp, Docker data, or cache volume full | Identify the exact filesystem and safe-to-clean data |
| CI build slower than local | Low CPU quota, slow storage, cold cache, network | Compare runner/cache specs and break down timing by phase |
| Peak RAM spikes after adding a library | Reachable graph/metadata/compilation paths changed | Inspect new dependency, overly broad reflection registration, and build logs |
| Multiple parallel builds all slow down or fail | CPU/RAM/disk contention | Reduce job concurrency or increase runner capacity |

Avoid concluding from a single symptom. For example, a slow build may stem from network dependency downloads or a missing toolchain rather than CPU. A native linking failure can also be caused by a missing system library rather than running out of RAM or disk.

## 12. Capacity Planning for CI/CD

Suppose a service runs a standalone native build with an observed peak memory of 14 GB on an 8-vCPU runner and finishes reliably. Do not assume a 16 GB runner can run **two builds simultaneously**: two jobs can generate combined memory demand well above 16 GB, before even counting the OS and build tools.

A sound planning approach:

1. **Measure a single build** on the exact intended toolchain and runner.
2. **Determine actual peak memory**, disk needed during build, and completion time (including both cold and warm caches).
3. **Leave headroom** for the OS, linker, incremental dependency growth, and runner variance.
4. **Size concurrency:** the number of concurrent jobs must fit total RAM, CPU, and disk budgets.
5. **Validate across several stable builds** on comparable commits and conditions before adopting as the standard CI configuration.

On low-RAM runners, running two services sequentially is sometimes faster overall than running both concurrently and hitting swap or OOM. On runners with spare CPU and RAM, parallelizing can reduce pipeline wait times.

### Illustrative Budgeting Example

Suppose each native job is measured at a peak of **12 GB job-level memory** and roughly **20 GB of additional workspace/cache space**. If a runner has 32 GB RAM and 80 GB free disk, before running two jobs concurrently you must still account for the OS, background processes, peak variance, and Docker storage. You cannot simply divide `32 / 12 = 2` and conclude two jobs will reliably fit.

The 12 GB and 20 GB figures here are **illustrative assumptions**, not consumption standards for Spring Boot/GraalVM.

## 13. Ways to Reduce Resource Pressure

If resource demands exceed available machines, tune in the following order:

**Trim unnecessary pipeline work.** Do not force every branch commit to run a full native build if testing needs allow earlier stages to run JVM/AOT checks first; schedule native builds at stages verifying compatibility and release readiness.

**Manage dependencies and metadata.** Remove genuinely unused libraries, avoid overly broad reflection/resource hints, and audit dynamic class registration. This can let GraalVM analyze less code, though impact must be measured; not every large dependency increases image size or peak RAM equally.

**Use appropriate caching.** Maven/Gradle dependency caches and Docker/Buildpacks caches can cut download/recreation time for certain inputs. Caches also consume disk; design retention policies and measure cold-cache cases too.

**Set sensible concurrency.** If the bottleneck is RAM, reducing job or thread concurrency is usually more effective than trying to raise heap. If the bottleneck is genuinely CPU and RAM headroom remains, a higher-core runner can cut build time.

**Use dedicated runners.** Offload native builds from laptops running IDEs, browsers, and databases; dedicated CI runners yield steadier results and easier monitoring.

**Do not arbitrarily trade away release quality.** Some optimization flags alter build time and runtime image characteristics. If you use a fast build mode for local iteration, re-test and re-measure on the exact release build configuration.

## 14. Practice: Measuring and Tuning the Same Project

The goal is to determine the right build configuration **by measurement**, not by guessing from JAR size or final image size.

**Preparation.** Pick a Spring Boot app with a simple endpoint, already configured for AOT/GraalVM Native Build Tools. Record the OS, JDK/GraalVM, plugin versions, vCPU count, RAM, free disk, and local/container build mode.

**Run 1 — baseline.** Build native with default settings. Measure wall-clock time, peak memory, CPU, and disk state. Confirm the executable runs and the endpoint returns the expected response.

**Run 2 — vary parallelism.** Keep source, toolchain, and cache policy identical; adjust Native Image thread count (if supported by your version). Record duration and peak RAM. If fewer threads lower RAM while lengthening build time, that is a normal trade-off.

**Run 3 — adjust heap limit when justified.** Only change `-J-Xmx` if logs or metrics prove heap is the bottleneck and the host has headroom. Compare build success, GC time if available, and peak memory.

**Run 4 — simulate CI.** Run in a container/runner with quotas matching deployment/CI, re-checking Docker/cache disk and concurrency. Do not use local runs as an automatic guarantee of CI success.

Record measurements in the template:

| Run | Allocated CPU | RAM/Quota | Heap Limit | Native Parallelism | Duration | Peak Memory | Result |
|---|---|---|---|---|---|---|---|
| Baseline | Fill in data | Fill in data | Default | Default | … | … | … |
| Thread tuning | Unchanged | Unchanged | Default | Test value | … | … | … |
| Heap tuning | Unchanged | Unchanged | Test value | Unchanged | … | … | … |
| Runner/CI | Per runner | Per runner | Per config | Per config | … | … | … |

An experiment is meaningful when changing **one group of variables at a time**, on the same commit, while documenting cache state. Runtime measurement (startup, post-startup RSS, throughput) is a separate step and must not be substituted with build metrics.

## 15. Summary

To compile Spring Boot into a GraalVM Native Image, provision **CPU for analysis and optimization**, **RAM for the compiler and auxiliary processes**, and **disk for dependency caches, AOT code, intermediate files, and container layers**. These demands vary by project and build environment; use reference sizing tables as a starting point, then finalize configuration based on observed peak memory, build duration, and actual runtime verification.

The three most important principles are: **measure your own pipeline's resources**, **reserve headroom for the entire environment rather than only Native Image heap**, and **control concurrent builds**. With those in place, the team can pick the right developer machine, CI runner, or builder container and evaluate native startup/memory benefits without build-time resource failures distorting the experiment.

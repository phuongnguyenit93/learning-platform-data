# Designing Runners with Sufficient RAM, CPU, and Disk for Native Compilation

## 1. Why Does Native Compilation Need a Dedicated Runner?

Compiling Spring Boot into a GraalVM Native Image is a heavy build workload. The Native Image builder runs on its own JVM, analyzes application reachability, creates representations for required classes/methods, optimizes code, and invokes the native compiler/linker to produce an executable. This process can consume significantly more RAM, CPU, and temporary disk space than a typical `mvn test` or `gradle test`.

An under-provisioned runner can exhibit several different symptoms:

- `OutOfMemoryError: Java heap space` when the Native Image builder heap reaches its limit.
- The process is OOM-killed by the kernel/container even though the logs show no Java exception.
- Prolonged builds due to CPU throttling or multiple jobs competing for resources.
- Disk exhaustion in the workspace, temp directory, Maven/Gradle cache, or Docker layers.
- Intermittent build passes and failures due to parallel load and fluctuating resource usage.

Good runner design looks simultaneously at **RAM, CPU, disk, container limits, and the number of concurrent native builds**. You cannot size a runner based solely on core count or solely on the heap allocated to the Native Image builder.

After this lesson, you will be able to:

- Read peak RSS and distinguish it from the builder's Java heap.
- Size RAM from application measurements with headroom for the OS, Maven/Gradle, and linker.
- Tune `--parallelism`, `-J-Xmx`, and the number of concurrent native builds.
- Calculate disk space required for sources, caches, outputs, temp files, and container layers.
- Choose an appropriate GitHub-hosted runner or self-hosted runner.
- Configure Maven/Gradle, Docker, and CI for stable, reproducible builds.

## 2. Understanding the Resources Used by the Native Image Builder

### 2.1. The Builder Runs on a JVM, the Output Executable Is Native

During the build step, the `native-image` command runs on a JVM. This JVM performs analysis and orchestrates compilation. GraalVM then invokes the native toolchain, such as the C compiler and linker, to generate an executable for the target OS/CPU.

Therefore, distinguish between these components:

| Component | Primary resources |
|---|---|
| Native Image builder | Java heap, metaspace, thread stacks, analysis data, and the builder's native structures |
| Native compiler/linker | RAM, CPU, and temporary files while compiling/linking object files |
| Maven/Gradle and plugins | Build tool JVM, daemon, test processes, dependency resolution |
| CI host/container | OS, Docker daemon, logging, caches, agent, and background processes |

`-J-Xmx` only sets the heap limit for the JVM running the Native Image builder. It does not cap the total RSS of the builder, native compiler, linker, Maven/Gradle, or the entire runner.

### 2.2. Heap Does Not Equal RSS

For example, configuring the builder with `-J-Xmx8g` does not mean the overall build uses at most 8 GB of RAM. RSS also includes:

- Committed heap of the builder.
- Metaspace, code cache, thread stacks, and JVM native memory.
- The native compiler/linker and child processes.
- Maven/Gradle daemons, test JVMs, and plugin processes.
- OS page cache, Docker daemon, and runner services.

Therefore, when sizing a runner, prioritize **job-wide peak RSS** or cgroup/container memory peak. Use the heap limit as a tuning knob, not as a proxy for total memory measurement.

### 2.3. Default Behavior by CI Environment

Native Image can automatically determine memory and thread counts based on system resources. Current GraalVM documentation describes a dedicated mode for containers/CI (typically detected via `CI=true`): the builder can use up to roughly 85% of available RAM as its heap limit, subject to a maximum cap depending on the GraalVM version. Actual usage can exceed the heap limit due to native memory and child processes.

By default, Native Image uses multiple processors to shorten build time, with threads capped at 32. You can lower the thread count with `--parallelism` to reduce CPU load and RAM usage, at the cost of longer builds.

Defaults and caps change across GraalVM versions. Check the Build Resources section in the documentation for the exact version installed on your runner, and inspect the build output to observe actual peak RSS. The [Native Image Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/) documentation describes how the builder selects heap and parallelism in CI.

## 3. Size RAM from Measurements, Not JAR Size Guesses

### 3.1. Factors That Increase Peak Memory

Peak memory typically increases when:

- The application has many reachable classes, large dependencies, or heavy framework configurations.
- Reflection, proxy, serialization, and resource metadata expand the analysis scope.
- Using `-H:Preserve=all`, PGO instrumentation, or options that retain extra metadata.
- Compilation thread count increases.
- Multiple native images are built in parallel on the same runner/container.
- Maven/Gradle daemons, test JVMs, or Docker builds run concurrently.

JAR size does not accurately predict peak RAM. Two JARs of similar size can have vastly different call graphs, reachable class counts, and analysis complexity.

### 3.2. Baseline Measurement Procedure

1. Select a clean runner and pin GraalVM/JDK, Maven or Gradle, and the native toolchain.
2. Build with the exact production profile, metadata, and container target.
3. Record peak RSS, builder heap limit, CPU time, wall-clock time, and peak disk usage.
4. Repeat the build at least a few times to observe variance from caching or concurrency.
5. Run an additional build under realistic CI conditions with container/cgroup limits matching the pipeline.

On Linux, you can use `/usr/bin/time -v` to capture `Maximum resident set size`:

```bash
/usr/bin/time -v ./mvnw -Pnative -DskipTests package
```

Or with Gradle:

```bash
/usr/bin/time -v ./gradlew nativeCompile
```

`time -v` provides the RSS measurement for the wrapped command, which is useful for comparing the same command across builds. It may not accurately capture the peak of the entire concurrent process tree; use cgroup `memory.peak` or job-level telemetry when planning runner RAM.

### 3.3. Measuring Memory Peak in Linux cgroups

On Linux using cgroup v2, you can read the following files if permitted by the runner/container:

```bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.events
```

- `memory.max`: the cgroup hard limit; a value of `max` means no hard limit at that cgroup level.
- `memory.current`: current memory in use at read time.
- `memory.peak`: highest memory usage since the cgroup was created.
- `memory.events`: event counters such as `oom` and `oom_kill`.

If the runner uses cgroup v1 or nested cgroups, file paths will differ. Use CI platform telemetry when these files cannot be read.

### 3.4. Calculating Runner RAM with Headroom

Take the highest peak RSS from a representative build, then add headroom for variance, the OS, the agent, and other build processes. A starting rule of thumb can be:

\[
RAM_{runner} \ge PeakRSS_{job} + Headroom_{OS,agent,variance}
\]

For a runner executing a single native build, you can start by adding 20–30% headroom on top of measured peak RSS; this is a **planning heuristic**, not a minimum mandated by GraalVM. If the job runs Docker-in-Docker, multiple modules, or multiple test processes, re-measure the full workload and increase headroom accordingly.

Do not add `-Xmx` on top of peak RSS again if peak RSS already measured the entire job; avoid double-counting the same memory.

### 3.5. Example Reading of Measurements

Suppose a native build yields these measurements:

| Metric | Illustrative value |
|---|---:|
| Native Image builder heap limit | 8 GiB |
| Job-wide peak RSS | 11.5 GiB |
| Peak CPU | 4 vCPUs nearly continuously |
| Build duration | 18 minutes |
| Peak disk in workspace/temp | 7 GiB |

Do not pick an 8 GiB runner just because the builder heap is 8 GiB; peak RSS already exceeds that. Adding 25% headroom to peak RSS gives a starting runner RAM target around 14.4 GiB, so select a tier with higher physical RAM and validate it.

## 4. Throttling CPU and Parallelism

### 4.1. CPU Affects Both Duration and RAM

Native Image runs multiple phases in parallel: analysis, compilation, code generation, and linking. Increasing thread count usually shortens build time but also increases the number of simultaneously live data structures and tasks, raising peak RAM.

Even if a runner has many cores, you should not necessarily use all of them. When memory is the bottleneck, lowering `--parallelism` can stabilize the build at the expense of longer duration.

### 4.2. Tuning `--parallelism`

Example limiting Native Image to 4 threads:

```bash
native-image --parallelism=4 -jar target/order-service.jar order-service
```

In Gradle Native Build Tools:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add('--parallelism=4')
        }
    }
}
```

In Maven Native Build Tools:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--parallelism=4</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

Each `buildArg` is a Native Image option token, not a full shell line. Keep values belonging to a single option inside the same `buildArg`.

### 4.3. Tuning the Native Image Builder Heap

You can set an absolute heap size:

```bash
native-image -J-Xmx8g --parallelism=4 -jar target/order-service.jar order-service
```

Or specify a percentage of the RAM detected by the builder:

```bash
native-image -J-XX:MaxRAMPercentage=60.0 --parallelism=4 -jar target/order-service.jar order-service
```

Choose a single heap-limiting strategy suited to your runner. Too little heap causes `OutOfMemoryError`; too much heap can starve the native compiler/linker or the OS. `-J-Xmx` caps the builder JVM, not the total RSS of the job.

On a 16 GiB runner, you can start by testing `-J-Xmx8g` and `--parallelism=4`, then adjust based on peak RSS. This is only a conservative starting configuration, not a universal formula for every application.

### 4.4. Avoid Multiplying Concurrency Across Build Tool and Native Image

A single job might concurrently run:

- Multiple Maven reactor modules via `mvn -T`.
- Multiple Gradle tasks/workers via `--parallel`.
- Multiple native image binaries.
- Multiple CI jobs on the same self-hosted runner.
- Native Image builder threads inside each binary.

If each native build uses 8 threads and the runner launches 3 builds simultaneously, total load can far exceed available CPU/RAM. For CI native compilation, start with **one native image build at a time per runner**; increase concurrency only after measuring headroom.

Gradle Native Build Tools caps the number of concurrent native image builds. By default this cap is based on CPU core count divided by 16; you can adjust it via `org.graalvm.buildtools.max.parallel.builds` in `gradle.properties` or the `GRAALVM_BUILDTOOLS_MAX_PARALLEL_BUILDS` environment variable. This controls parallel image builds, which is distinct from `--parallelism` controlling threads within a single image build.

`gradle.properties` example:

```properties
org.graalvm.buildtools.max.parallel.builds=1
```

In multi-module Maven builds, avoid enabling `-T` for modules that trigger native compilation unless the runner has ample resources. You can compile/test JVM modules in parallel, while serializing the native build step in the pipeline.

## 5. Disk Space Planning

### 5.1. Directories That Consume Disk

A native build can generate far more data than the final executable:

- Source checkout and generated sources.
- Maven repository `.m2/repository` or Gradle caches.
- GraalVM distribution, native compiler, and system packages.
- `target/`, `build/`, AOT generated sources/classes.
- Native Image temporary files, object files, and linker outputs.
- Native executable, debug symbols, and build reports.
- Docker build context, image layers, intermediate layers, and image archives.
- Test reports, logs, tracing metadata, and retained artifacts.

Peak disk usage is the sum of everything existing simultaneously. Looking only at the final executable size will underestimate disk requirements.

### 5.2. Measuring Disk Before, During, and After the Build

On Linux:

```bash
df -h
du -sh "$GITHUB_WORKSPACE" 2>/dev/null || true
du -sh "$HOME/.m2/repository" 2>/dev/null || true
du -sh "$HOME/.gradle/caches" 2>/dev/null || true
docker system df 2>/dev/null || true
```

Record free space before running the native build. After the build, inspect the workspace, temp directories, and Docker storage again. On self-hosted runners, monitor disk across multiple jobs because caches, old workspaces, and image layers can accumulate.

### 5.3. Estimating Required Disk

Plan by component:

\[
Disk_{required} = Checkout + DependencyCache + BuildTemp + Outputs + ContainerLayers + Headroom
\]

Measure each term in a representative pipeline. If building container images, include the base image, application layer, debug layer, and image archive if CI exports one. Leave enough free space for the native compiler to write temporary files while final outputs have not yet been cleaned up.

### 5.4. Selective Cleanup

- Use ephemeral runners when possible so workspaces and container layers are discarded after the job.
- Cache Maven/Gradle dependencies and wrapper distributions; key caches by OS, architecture, JDK/GraalVM, and lockfiles.
- Do not cache entire `target/` or `build/` directories across runners with different OS/architecture/GraalVM versions.
- Prune old Docker images/layers on self-hosted runners according to a retention policy.
- Upload executables, test reports, and build reports as artifacts before workspace cleanup.
- Do not delete caches currently in use by other jobs on shared runners.

### 5.5. Disk and Container Builds

If CI runs the native build inside a Docker container, account for Docker daemon storage on the host. Deleting files inside a container does not necessarily reclaim layers of already-built images. Use `docker system df` to inspect usage and run controlled pruning on dedicated runners.

## 6. Choosing GitHub-Hosted vs. Self-Hosted Runners

### 6.1. Standard Runners Are a Baseline, Not a Guarantee of Build Success

According to current GitHub-hosted runner specifications, standard sizing depends on repository visibility. For example, Linux x64 standard runners for public repositories provide 4 vCPU, 16 GB RAM, and 14 GB SSD; standard runners for private repositories provide 2 vCPU, 8 GB RAM, and 14 GB SSD. These resources are limited—in particular, 14 GB of disk can be tight when holding dependency caches, build temp files, and Docker layers at the same time.

Runner specifications can change by repository type, plan, image, and over time. Always check the provider's runner table before deciding.

### 6.2. Example Larger Runner Tiers

GitHub larger runners currently offer reference configurations such as:

| vCPU | RAM | SSD | Reference use case |
|---:|---:|---:|---|
| 2 | 8 GB | 75 GB | Small build needing more disk than standard runners |
| 4 | 16 GB | 150 GB | Medium native build, if measured peak RSS fits |
| 8 | 32 GB | 300 GB | Heavier native build or faster build times needed |
| 16 | 64 GB | 600 GB | Large application, native tests, or multi-step pipeline |
| 32 | 128 GB | 1,200 GB | Very large build or controlled parallel native workloads |

These are example tiers from one provider, not GraalVM RAM/CPU requirements. Pick a tier based on measured peak RSS, CPU time, peak disk, and actual build cost.

### 6.3. When to Use Self-Hosted Runners?

Self-hosted runners are useful when:

- Large RAM/disk or dedicated NVMe storage is required.
- Long-lived dependency/toolchain caches are needed.
- Native builds target multiple architectures or specialized OSes.
- You want tight control over compiler/linker versions and base images.
- Native builds are too long or exceed hosted runner resources.

In return, you must operate cleanup, security patching, job isolation, disk/RAM monitoring, and ensure jobs do not share a mutating workspace. Runners with production secrets must not run untrusted pull request code on the same host.

## 7. Container and cgroup Limits

### 7.1. Host RAM Is Not Always the RAM Visible to the Builder

If a native build runs inside Docker or a Kubernetes pod, the builder may be constrained by cgroup memory. For instance, if the host has 64 GB RAM but the container is only allocated 12 GB, Native Image must operate within that container limit.

Docker allows setting hard memory limits and CPU quotas. When a container is constrained, measure inside the container/cgroup rather than only checking `free -h` on the host.

### 7.2. Do Not Set Heap Equal to Total Container Memory

For example, in a container with a 16 GB limit, do not set `-J-Xmx16g` for the builder. You must still reserve RAM for:

- Metaspace, thread stacks, and native memory of the JVM builder.
- The native compiler/linker.
- Maven/Gradle processes and plugins.
- Shell, Docker runtime, logging, and agents inside the container.

Start with a heap substantially lower than the container limit, then inspect peak RSS and adjust. If `memory.events` increments `oom_kill`, inspect child processes and the whole job rather than just raising `-Xmx`.

### 7.3. Docker Limits Example

```bash
docker run --rm \
  --memory=16g \
  --cpus=4 \
  -v "$PWD:/workspace" \
  -w /workspace \
  ghcr.io/example/native-build-image:graalvm \
  ./mvnw -Pnative -DskipTests package
```

The example above caps the container at 16 GB and 4 CPUs. This is illustrative; the Native Image builder heap and `--parallelism` still need to be configured separately based on measurements.

## 8. Configuring Maven and Gradle for Resource-Constrained Runners

### 8.1. Maven Native Build Tools

```xml
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
```

If a parent POM already declares `buildArgs`, use Maven's appropriate merge mechanism in child modules, such as `combine.children="append"`, so you do not accidentally wipe out shared options like `--no-fallback`.

### 8.2. Gradle Native Build Tools

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.addAll(
                    '-J-Xmx8g',
                    '--parallelism=4'
            )
        }
    }
}
```

If native tests are also built, configure the `test` binary separately or use `binaries.all` only when both binaries genuinely need the same limits. Avoid applying inappropriate heap/parallelism settings to a lighter test image.

### 8.3. Limiting the Gradle Daemon and Worker Count

The Native Image builder is a separate JVM controlled by `-J-Xmx`; the Gradle daemon has its own heap configured via `org.gradle.jvmargs`:

```properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
org.gradle.workers.max=2
org.graalvm.buildtools.max.parallel.builds=1
```

These values are examples for a small runner. Total memory is still Gradle daemon + Native Image builder + child processes + OS. Do not stack multiple native builds just because Gradle can run tasks in parallel.

### 8.4. Distinguishing the Limits

| Configuration | Controls |
|---|---|
| `-J-Xmx8g` | Java heap of the Native Image builder |
| `-J-XX:MaxRAMPercentage=60.0` | Builder heap percentage of RAM detected by the JVM |
| `--parallelism=4` | Maximum threads for a single native image build |
| `org.gradle.workers.max=2` | Number of Gradle workers that can execute concurrently |
| `org.graalvm.buildtools.max.parallel.builds=1` | Number of native image builds the Gradle plugin runs concurrently |
| Docker `--memory=16g` | Hard memory limit of the container |
| Docker `--cpus=4` | CPU quota of the container |

Do not confuse these limits with one another. Raising `-Xmx` does not fix CPU throttling; adding CPU does not fix a full disk; reducing Gradle workers does not automatically limit threads inside Native Image unless `--parallelism` is configured.

## 9. GitHub Actions Pipeline Example

The example below illustrates a dedicated native build job running on a self-hosted runner labeled `native-image-large`. The runner must have GraalVM, `native-image`, and a compatible C/C++ toolchain pre-installed before picking up the job.

```yaml
name: native-build

on:
  pull_request:
  push:
    branches: [main]

jobs:
  native:
    runs-on: [self-hosted, linux, x64, native-image-large]
    timeout-minutes: 60
    env:
      CI: "true"
    steps:
      - uses: actions/checkout@v4

      - name: Inspect runner resources
        shell: bash
        run: |
          nproc
          free -h
          df -h
          java -version
          native-image --version
          native-image --native-image-info

      - name: Build native executable
        shell: bash
        run: |
          /usr/bin/time -v ./mvnw -Pnative -DskipTests package

      - name: Inspect output and disk
        if: always()
        shell: bash
        run: |
          df -h
          du -sh target 2>/dev/null || true
          find target -maxdepth 2 -type f -printf '%s %p\n' 2>/dev/null | sort -nr | head -30

      - name: Upload native executable
        if: success()
        uses: actions/upload-artifact@v4
        with:
          name: order-service-native
          path: target/order-service
```

In production, pin GitHub Actions versions per organizational security policy and provision GraalVM/toolchains via a vetted setup step or immutable runner image. Do not assume the `native-image-large` label exists by default; it is an organization-managed self-hosted runner label.

If using GitHub-hosted runners, replace `runs-on` with the label matching your plan/repository. Check the runner specification table because public and private repositories may receive different CPU/RAM allocations under similar labels.

## 10. Choosing a Runner by Workload

No single tier fits every project. The following table is a starting point for benchmarking, not a minimum system requirement:

| Workload | Starting point to test | What to measure |
|---|---|---|
| Small module, few dependencies, no container build | 4 vCPU/16 GB runner or equivalent | Peak RSS, build duration, temp disk |
| Spring Boot service with many starters, AOT, and metadata | 8 vCPU/32 GB runner or equivalent | RSS across parallelism levels, compiler/linker time, peak disk |
| Large monolith, heavy integration and native tests | 16 vCPU/64 GB runner or equivalent | Peak RSS of main/test images, concurrency, and container layers |
| Multi-module reactor with multiple native binaries | 16 vCPU/64 GB+ runner or split jobs by module | Concurrent image builds, disk cache, and memory peak |

Only scale up the runner tier when measurements show CPU/RAM/disk is the bottleneck. If builds are slow due to dependency downloads or Docker image pulls, adding CPU/RAM may not address the root cause.

## 11. Diagnosing Resource Failures

| Symptom | Possible cause | Remediation |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Builder heap too low or analysis needs more heap | Check `-J-Xmx`, reduce `--parallelism`, or use a larger-RAM runner |
| Job OOM-killed with no Java stack trace | Total RSS exceeded cgroup/host limit; native compiler or child process was killed | Read `memory.events`, `memory.peak`, runner telemetry; lower concurrency and heap or raise memory limit |
| Build very slow despite many CPUs | Low CPU quota, compiler/linker throttled, disk I/O, or dependency downloads | Check cgroup CPU throttling, I/O, caching, and toolchain |
| Unusually high RAM peak | Multiple native builds/Gradle workers running concurrently | Set `org.graalvm.buildtools.max.parallel.builds=1`, reduce workers and `--parallelism` |
| Out of disk mid-compilation | Temp files, caches, outputs, and Docker layers coexisting | Measure `df -h`, switch to larger disk runner, clean caches carefully, or reduce intermediate artifacts |
| Intermittent build failures on hosted runners | CPU/RAM tiers differ by repository visibility or job concurrency | Verify actual runner specs, pin a larger tier, or move to self-hosted |
| Docker build OOMs while host still has free RAM | Container memory limit is lower than host RAM | Inspect cgroup inside container and adjust `--memory`/pod limit |
| Raising `-Xmx` still leads to OOM-kill | Heap is not all of RSS; native memory/linker/OS lack headroom | Lower heap/parallelism or increase total RAM; do not just raise Xmx |
| Cache speeds up runner initially but fills disk later | Caches and workspaces accumulate on self-hosted runners | Use ephemeral runners or a retention/cleanup policy |
| Building x64 native binary on an ARM64 runner | Architecture/toolchain mismatch or unsupported cross-compilation | Choose a runner matching target OS/architecture or configure cross-compilation per GraalVM docs |

## 12. Hands-On Exercise: Measure and Size a Runner for order-service

**Context:** `order-service` includes Spring Web, Data JPA, Actuator, Flyway, and the PostgreSQL driver. The pipeline needs to build a native executable, run native smoke tests, and package an OCI image.

### Step 1 — Establish a Baseline

Run the native build on your current runner. Record:

- Actual CPU, RAM, disk, and architecture of the runner.
- GraalVM/JDK, Maven/Gradle, C compiler, and linker versions.
- Job-wide peak RSS, builder heap, CPU utilization, and build duration.
- Free disk before the build, peak disk, and Docker layer sizes after the build.

### Step 2 — Test Parallelism Tuning

Run configurations with `--parallelism=2`, `4`, and `8` (if the runner has enough CPU/RAM). Keep heap constant or note any changes explicitly. Compare build duration, peak RSS, and CPU throttling.

### Step 3 — Test Heap Limits

With a chosen parallelism, test `-J-Xmx` or `-J-XX:MaxRAMPercentage`. Do not vary multiple parameters at once; changing heap and parallelism simultaneously makes it hard to determine which factor changed the outcome.

### Step 4 — Test Container Limits

Run the build inside a container with memory/CPU limits close to the CI configuration. Inspect cgroup peak and OOM events. Confirm the container has sufficient disk for the workspace, temp files, and Docker output.

### Step 5 — Select the Runner Tier

Pick the lowest tier that still satisfies:

- Consistent repeatable builds with no OOMs and no disk exhaustion.
- Headroom above peak RSS for workload growth/variance.
- No significant CPU/disk throttling.
- Build duration within desired CI time budgets.
- Toolchain/architecture matching the image to be deployed.

### Step 6 — Record the Configuration

Commit the measured settings into `pom.xml`/`build.gradle`, runner labels, container limits, and the CI job. Record the GraalVM version alongside the measurements so future upgrades have a comparison baseline.

### Results Sheet

| Metric | Baseline | Chosen config |
|---|---:|---:|
| Runner vCPU | _(record)_ | _(record)_ |
| Runner RAM | _(record)_ | _(record)_ |
| Runner disk | _(record)_ | _(record)_ |
| Container memory limit | _(record)_ | _(record)_ |
| `-J-Xmx` or MaxRAMPercentage | _(record)_ | _(record)_ |
| `--parallelism` | _(record)_ | _(record)_ |
| Concurrent native builds | _(record)_ | _(record)_ |
| Peak RSS | _(record)_ | _(record)_ |
| Peak disk usage | _(record)_ | _(record)_ |
| Build duration | _(record)_ | _(record)_ |
| OOM/disk failures | _(record)_ | _(record)_ |

## 13. Key Takeaways

The Native Image builder runs on a JVM, but total build resource consumption also includes the native compiler/linker, Maven/Gradle, the OS, and the container runtime. Size RAM based on job-wide peak RSS rather than treating `-Xmx` as total memory. Throttle `--parallelism`, Gradle workers, and concurrent image builds to avoid multiplying load. Budget disk for caches, temp files, AOT outputs, native artifacts, and container layers; monitor disk on both hosted and self-hosted runners.

The right runner is one that builds reliably and reproducibly, leaves headroom for variance, and matches the target OS/architecture toolchain. Start from baseline measurements, change one variable at a time, and pick a cost-effective tier. There is no single fixed RAM/CPU number that fits every Spring Boot Native Image project.

### Official References

- [GraalVM — Native Image Build Output and Build Resources](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/)
- [GraalVM — Native Image Build Configuration](https://www.graalvm.org/reference-manual/native-image/BuildConfiguration/)
- [GraalVM — Native Image Command-line Options](https://www.graalvm.org/latest/reference-manual/native-image/overview/Options/)
- [GraalVM Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin)
- [GraalVM Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin.html)
- [GitHub Actions — GitHub-hosted Runners Reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [GitHub Actions — Larger Runners Reference](https://docs.github.com/en/actions/reference/runners/larger-runners)
- [Docker — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/)

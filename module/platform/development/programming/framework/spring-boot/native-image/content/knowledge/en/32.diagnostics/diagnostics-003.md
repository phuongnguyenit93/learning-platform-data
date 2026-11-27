# Build Terminated Due to Insufficient RAM, Timeout, or Runner Resource Limits

## Lesson Objectives

A Native Image build is a heavy workload. This process runs the Native Image builder, performs reachability analysis, optimizes and compiles machine code, and then produces an executable. With Spring Boot, the build also includes a Spring AOT step to generate code and metadata before native compilation begins.

When a build stops midway, a "failed" message or the last log line is not enough to identify the root cause. The builder JVM may have run out of heap, the container may have been OOM-killed by the kernel, the CI job may have timed out, CPU may be throttled, the disk may be full, or the runner may have hit resource limits. Each case requires different evidence and a different fix.

After this lesson, you will be able to:

- Distinguish a Native Image builder Java heap OOM from a container/host OOM kill.
- Read build logs to identify the last phase and the exact point where the build stopped.
- Inspect CPU quota, memory/cgroup, disk, inodes, and the temporary directory.
- Tune builder heap and parallelism in a controlled way.
- Handle CI timeouts, Docker resource limits, and Kubernetes runner/job limits.
- Design retry, log collection, and build monitoring workflows to prevent recurring failures.

## 1. Understand the Native Image Build Process Properly

### 1.1. The Builder JVM Differs from the Resulting Native Executable

When running `native-image`, the toolchain launches the Java-based Native Image builder. The builder JVM analyzes the application, constructs the image heap, and compiles reachable methods. The final output is a native executable that runs independently of a JVM.

Therefore, during the build phase, you must distinguish two categories of resources:

- **Builder resources:** the build process's Java heap, builder native memory, compiler threads, temporary files, and compiler/linker subprocesses.
- **Native application resources:** managed heap/runtime memory, thread stacks, native allocations, shared libraries, and application data when the executable runs.

A native application with a small runtime RSS does not mean compiling it requires little RAM. The builder can require significantly more memory than the resulting executable at runtime.

### 1.2. Steps That May Appear in the Build Log

Phase names and display formatting depend on the GraalVM version, but logs typically show the following work:

1. Initializing the builder and features.
2. Analyzing reachability, types, fields, methods, and the object graph.
3. Processing class initialization and metadata.
4. Optimizing/inlining methods.
5. Compiling methods into machine code.
6. Laying out code and creating the image.
7. Linking and writing the executable along with additional artifacts.

If the build stops during Analysis, inspect the graph and builder memory. If it stops during Compiling Methods, inspect method counts, CPU, compiler threads, and duration. If it stops during Creating Image or linking, check memory, disk, the temporary directory, and the native toolchain.

### 1.3. A Build Has Multiple Limit Layers

| Layer | Applicable limits |
|---|---|
| Native Image builder JVM | `-J-Xmx`, JVM options, and number of compiler threads |
| Docker/container | CPU quota, memory limit, PID limit, ephemeral storage |
| Kubernetes | requests/limits, node allocatable, ephemeral storage, pod eviction |
| CI runner | Actual RAM/CPU, job timeout, disk quota, concurrency |
| Host/VM | Host OOM, swap policy, filesystem, inodes, and contention |

A build succeeds only when every layer has sufficient resources throughout the entire run.

## 2. Classify the Failure Before Changing Configuration

### 2.1. Common Symptoms

| Symptom | Possible cause | Evidence to look for |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Builder JVM heap is insufficient | Builder JVM logs, heap dump if any, `-J-Xmx` setting |
| Container exit code 137 or `OOMKilled` | Kernel kill due to exceeding memory limit or external SIGKILL | Container state, cgroup memory events, host/kernel logs |
| CI job canceled after a fixed duration | Job timeout or workflow timeout | CI job summary, timeout configuration, timestamps |
| Build slows down, low CPU or high throttling | Low CPU quota, host contention, or I/O wait | CPU usage, throttled periods, process state, disk metrics |
| `No space left on device` | Out of disk space or inodes | `df -h`, `df -i`, temp/workspace size |
| Build stops during image creation/linking | Temporary storage, linker, or native toolchain | Tail logs, disk space, linker output, and exit code |
| Process vanishes without a stack trace | Runner/host kill, timeout, or OOM kill | CI events, container status, kernel events |

Do not conclude OOM from exit code 137 alone. This code typically corresponds to SIGKILL, which can result from an OOM kill, a timeout controller, or an external kill action.

### 2.2. Collect Evidence Before Retrying

Before re-running, save:

- Full stdout/stderr of both the native build and Spring AOT.
- Exit codes of the build command and container/job.
- Start timestamp, last phase reached, and stop timestamp.
- GraalVM/JDK version, OS, architecture, and build arguments.
- CPU, memory limits/requests, and available CPUs.
- Disk usage, inode usage, and temporary directory location.
- CI job summary or Kubernetes termination reason.

Retrying immediately without saving details can destroy evidence of OOM events, timeouts, or runner state.

### 2.3. Check Whether the Build Process Is Still Running or Was Killed

On a Linux runner, you can observe:

```bash
ps -eo pid,ppid,stat,%cpu,%mem,rss,etime,args \
  | grep -E 'native-image|Native Image|java'
```

If the process still exists, inspect CPU, RSS, elapsed time, and process state. If the process has disappeared, cross-reference the exit code and container/runner events. Do not rely solely on a lack of new log lines to conclude the process is hung.

## 3. Diagnose Builder JVM Heap Exhaustion

### 3.1. Identify Java Heap OOM

Messages such as:

```text
java.lang.OutOfMemoryError: Java heap space
java.lang.OutOfMemoryError: GC overhead limit exceeded
```

indicate that the builder JVM does not have enough Java heap or is spending excessive time garbage collecting. This is different from the kernel OOM-killing the entire container.

With `Java heap space`, the builder JVM can usually print a stack trace and exit with a clear error. However, if the container is killed by the kernel before the JVM flushes logs, you may not see `OutOfMemoryError`.

### 3.2. Increase Builder Heap with `-J-Xmx`

`-J-` passes a JVM option to the Java process running the Native Image builder. For example:

```bash
native-image \
  -J-Xmx6g \
  -jar target/payment-service.jar
```

`-J-Xmx6g` sets the builder JVM's maximum Java heap to approximately 6 GiB. It does not set a heap cap on the resulting native executable.

Choose the value based on the runner's available memory. If a container has an 8 GiB memory limit, setting the builder heap to 8 GiB leaves insufficient headroom for:

- Builder JVM metaspace, code cache, and thread stacks.
- Graal compiler native allocations.
- C compiler/linker and subprocesses.
- File cache, memory mappings, and the operating system.

Start with a sufficient heap, measure peak container memory, and increase incrementally. Never set the heap beyond the cgroup limit.

### 3.3. Distinguish `-J-Xmx` from `-Xmx`

| Option | Applies to |
|---|---|
| `-J-Xmx6g` | The JVM running the Native Image builder |
| `-Xmx` when running `java -jar app.jar` | A JVM running a standard application |
| Native Image runtime heap options | The native executable's managed heap, per GraalVM version support |

Passing `-Xmx` alone to the `native-image` command does not replace `-J-Xmx`. Check `native-image --help` and the documentation for your exact version to confirm supported options.

### 3.4. Collect a Heap Dump When Needed

When the builder JVM can write a dump before running out of heap, you can add JVM options:

```bash
native-image \
  -J-Xmx6g \
  -J-XX:+HeapDumpOnOutOfMemoryError \
  -J-XX:HeapDumpPath=build/diagnostics \
  -jar target/payment-service.jar
```

Heap dumps can be large and contain data from the build process. Ensure the directory has enough disk space, restrict access permissions, and never upload dumps as public artifacts. Not every OOM produces a dump; a kernel SIGKILL may happen first.

## 4. When a Container or Runner Is OOM-Killed

### 4.1. Check Actual Memory Limits

On Linux, check:

```bash
free -h
cat /proc/meminfo
```

In cgroup v2, commonly inspected files include:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
```

`memory.current` shows current memory usage; `memory.max` is the limit (or `max` if there is no hard limit); `memory.events` records events such as `oom` and `oom_kill`.

Paths and filenames differ on cgroup v1 or when a process sits in a nested cgroup. Read `/proc/self/cgroup` and mount information to locate the builder's exact cgroup.

### 4.2. Compare Container Memory Against Builder Heap

Example:

| Metric | Illustrative value |
|---|---:|
| Container memory limit | 8 GiB |
| Builder JVM max heap | 6 GiB |
| Metaspace, thread stacks, code cache | 700 MiB |
| Compiler/linker/native memory and overhead | 1.5 GiB |

The total can exceed 8 GiB even before the Java heap hits `-Xmx`. That is why you must measure cgroup memory/peak rather than monitoring Java heap alone.

These numbers only illustrate how the budget adds up; actual components and usage vary by application, toolchain, and runner.

### 4.3. Identify OOM in Kubernetes

Inspect the pod and container state:

```bash
kubectl describe pod <pod-name>
kubectl get pod <pod-name> -o wide
kubectl get events --sort-by=.lastTimestamp
```

Look for:

- `Reason: OOMKilled`.
- Exit code 137.
- Container restart count.
- Node memory pressure and eviction events.
- Job/pod resource limits.

If a pod is `OOMKilled`, increasing the builder heap is not the first solution. You need to increase the memory limit/runner capacity or reduce the build's peak memory.

### 4.4. Identify Host OOM

If the build runs directly on a VM/runner, check kernel logs if permissions allow:

```bash
dmesg -T | grep -i -E 'out of memory|killed process'
```

On systemd-based systems, you can inspect the kernel or system journal depending on runner permissions. If the host OOM killer targets the builder JVM or linker process, CI logs may only record an abnormal process exit.

## 5. CPU Quota and Compiler Parallelism

### 5.1. Slow Builds Due to CPU Throttling

Native compilation can utilize many cores. If a runner only allocates a fraction of a CPU, the build can take significantly longer even with plenty of memory.

Check:

- Container CPU quota/cpuset.
- CPU usage and throttled periods.
- Number of compiler threads.
- CPU contention from other jobs.
- Duration of each build phase.

Do not immediately increase the timeout if the build is continuously throttled. First determine whether the runner has enough CPU or whether parallelism should be reduced.

### 5.2. Reduce Parallelism to Lower Peak Memory

Some GraalVM versions provide a `--parallelism` option to limit concurrent operations during the build. For example, if supported by your current version:

```bash
native-image \
  --parallelism=4 \
  -J-Xmx6g \
  -jar target/payment-service.jar
```

Reducing parallelism can decrease concurrent compiler/analysis tasks and lower peak resource usage, though it usually lengthens build time. Option names and scope depend on the GraalVM version; verify with `native-image --help` before use.

Do not pick a thread count based solely on physical core count. Runners have their own CPU quotas, memory limits, and contention levels. Benchmark different parallelism levels under the same resource constraints.

### 5.3. Distinguish CPU-Bound from Memory-Bound

| Symptom | Likelihood | Verification test |
|---|---|---|
| High CPU, memory headroom remains, long compile phase | CPU-bound | Increase CPU quota or use a faster runner |
| RSS near limit, heavy GC, OOM | Memory-bound | Increase memory/headroom or reduce parallelism |
| Low CPU, low RSS, high elapsed time | I/O wait or process blocked | Check disk, temp directory, linker, and process state |
| High CPU throttling | CPU quota-bound | Increase quota in a controlled measurement |

## 6. Diagnose CI Timeouts

### 6.1. Distinguish Job Timeouts from Command Timeouts

CI can terminate a build because:

- The workflow/job has an overall time limit.
- A step or command wrapper has its own timeout.
- The runner was preempted or lost connectivity.
- A user or automation canceled the job.

If logs stop at a fixed elapsed timestamp, check timeout configurations before adjusting GraalVM memory.

### 6.2. Compare Build Duration Against the Timeout

Record the duration of each step:

- Dependency resolution.
- Compiling and packaging the JVM artifact.
- Spring AOT processing.
- Native Image analysis.
- Native compilation.
- Linking and container packaging.

If native compilation alone consumes most of the time, set the job timeout based on actual build time distribution and runner variance. If dependency resolution or image pulls take most of the time, raising the native build timeout targets the wrong bottleneck.

### 6.3. Increase Timeouts Based on Evidence

Before increasing a timeout:

1. Confirm the build is still making progress via logs/CPU/memory.
2. Identify the active phase and its duration.
3. Rule out OOM, full disk, and CPU throttling.
4. Compare against successful build times on an equivalent runner.
5. Set a timeout with reasonable headroom and alert if builds exceed the baseline.

A longer timeout only allows work to run longer; it does not make the build faster.

### 6.4. Avoid Infinite Retries

Retries can help with transient runner disruptions, but they will not fix an under-provisioned RAM configuration or an oversized dependency graph. Cap retry counts, preserve logs per attempt, and distinguish transient errors from deterministic ones.

If the same source/toolchain consistently stops at the same phase with the same memory footprint, investigate build inputs/resources instead of repeating the job indefinitely.

## 7. Check Disk, Inodes, and Temporary Directory

### 7.1. Native Builds Use Temporary Storage

The Native Image builder and compiler/linker can create many intermediate files. The workspace and temp directory need enough space for:

- Extracted dependencies and build artifacts.
- Generated Spring AOT sources/classes.
- Native Image intermediate files.
- Object files, linker outputs, and debug information.
- Heap dumps or diagnostic logs if enabled.

`No space left on device` can occur when a filesystem runs out of either disk blocks or inodes. Both cases must be checked separately.

### 7.2. Check Disk Space and Inodes

```bash
df -h
df -i
du -sh "$PWD" "${TMPDIR:-/tmp}"
```

Inspect the actual filesystems backing the workspace and temp directory. Inside a container, temp may reside on ephemeral storage or a filesystem with a separate quota.

Never delete intermediate files while the builder is still running. After the job completes, clean up only temporary build directories belonging to that specific job/workspace.

### 7.3. Choose a Temporary Directory with Enough Space

If `/tmp` is small or on a filesystem with a low quota, you can point `TMPDIR` to a suitable mount before running the build:

```bash
mkdir -p "$PWD/build/native-tmp"
export TMPDIR="$PWD/build/native-tmp"
native-image -J-Xmx6g -jar target/payment-service.jar
```

Ensure the directory exists, is writable, and sits on a volume with sufficient space. Use consistent storage types when benchmarking build times; slow filesystems can prolong linking and temporary file operations.

## 8. Configure Builds via Maven, Gradle, and Buildpacks

### 8.1. Gradle Native Build Tools

Example build arguments configuration:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add("-J-Xmx6g")
            buildArgs.add("--parallelism=4")
        }
    }
}
```

Verify that your Gradle plugin and GraalVM versions support these arguments. Set values according to the runner's actual memory/CPU. Do not push the heap right up against the memory limit just because the build runs inside a container.

### 8.2. Maven Native Build Tools

Example:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-J-Xmx6g</buildArg>
            <buildArg>--parallelism=4</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

This is an illustrative configuration for `native-maven-plugin`. If the project uses the Spring Boot Maven plugin or a separate execution/profile, pass build arguments to the exact execution performing Native Image compilation.

### 8.3. Building with Cloud Native Buildpacks

When using `spring-boot:build-image` or `bootBuildImage`, Native Image may run inside a builder container managed by the buildpack. In that case, check:

- Resource limits of the builder container.
- Memory/CPU allocated to the builder by the Docker daemon or CI runner.
- Environment variables and build arguments accepted by the buildpack.
- The image build step timeout and CI job timeout.
- Docker daemon disk/ephemeral storage.

Do not assume `-J-Xmx` configured in the native plugin automatically applies to the buildpack. How arguments are passed and resources allocated depends on the builder/buildpack version; confirm via buildpack logs and version-specific documentation.

### 8.4. Record the Actual Configuration Used

Save these values:

- GraalVM/JDK version.
- Native Build Tools plugin version.
- Builder image and buildpack versions if applicable.
- Final Native Image arguments.
- Runner and builder container CPU/memory/disk limits.
- CI timeout and concurrency.

Do not rely solely on config files in the repository; logs must show which profile/task ran and which arguments were actually passed.

## 9. Collect Logs and Metrics to Pinpoint Bottleneck Phases

### 9.1. Keep Complete Build Output

In CI, retain full stdout/stderr with timestamps. Do not save only the last few lines because errors may appear well before the runner is killed.

You can export machine-readable build output if supported by your GraalVM version:

```bash
native-image \
  -H:BuildOutputJSONFile=build/native/native-build-output.json \
  -J-Xmx6g \
  -jar target/payment-service.jar
```

The JSON can help track phase durations, resource usage, and analysis metrics depending on the schema version. Verify the file was actually generated after the build and store the schema/toolchain version alongside it.

### 9.2. Use Build Report When Supported by the Toolchain

If your GraalVM distribution supports the HTML Build Report, you can add `--emit build-report` to inspect the Code Area, Image Heap, Resources, and SBOM.

Build Report helps locate components inflating image size or widening the reachable graph. It does not replace runner CPU/memory metrics and does not directly explain CI timeouts. If no report is generated, check the edition/version and rely on available build output.

### 9.3. Track Metrics Per Phase

Create a table for each build:

| Phase | Duration | CPU | Peak memory | Notes |
|---|---:|---:|---:|---|
| Spring AOT | ... | ... | ... | Generated sources |
| Analysis | ... | ... | ... | Reachability graph |
| Compilation | ... | ... | ... | Compiler threads |
| Image creation/linking | ... | ... | ... | Disk/temp/linker |
| Packaging | ... | ... | ... | Container/image layer |

Fill in actual measurements from logs and monitoring. Do not extrapolate phase durations if the toolchain does not report timing checkpoints.

## 10. Remediation Workflows by Symptom

### 10.1. Builder JVM Reports Java Heap OOM

1. Save the stack trace and heap dump if generated.
2. Check the current `-J-Xmx` setting.
3. Measure container/host memory and confirm remaining headroom.
4. Increase builder heap incrementally without exceeding the cgroup limit.
5. If peak memory remains high, reduce parallelism if supported by the version.
6. Inspect dependencies/reachability and class initialization.
7. Rebuild and compare peak RSS, duration, and phases.

### 10.2. Container Is OOMKilled

1. Confirm `OOMKilled` and the cgroup `oom_kill` event.
2. Check the memory limit and peak container memory.
3. Compare builder heap against off-heap memory usage.
4. Increase runner/builder memory if capacity permits.
5. Reduce parallelism or split CI load to lower contention.
6. Do not only increase `-J-Xmx`, because a larger heap can push total memory over the limit even sooner.

### 10.3. CI Job Times Out Without Process OOM

1. Confirm the job timeout/cancellation reason.
2. Inspect the final phase and log progress.
3. Check CPU throttling, disk I/O, and runner contention.
4. Use an appropriately sized runner or reduce parallel job concurrency.
5. Optimize dependencies/metadata if the analysis phase has grown.
6. Adjust the timeout based on measured build times plus headroom.

### 10.4. Build Is Slow with Low CPU

1. Check CPU quota and throttled periods.
2. Determine whether the builder is waiting on I/O or memory.
3. Test on a runner with a higher CPU quota.
4. Compare duration using the same memory and parallelism settings.
5. Increase parallelism only when both CPU and memory have sufficient headroom.

### 10.5. Disk Full or Linker Failure

1. Save linker logs and the exit code.
2. Check `df -h`, `df -i`, the workspace, and the temp mount.
3. Identify which outputs/intermediates are consuming space.
4. Provision adequate ephemeral storage or volume capacity.
5. Point the temp directory to a location with enough space.
6. Clean up the workspace after the job finishes while keeping diagnostic artifacts.

## 11. Design Stable CI Runners

### 11.1. Avoid Too Many Concurrent Native Builds

Native compilation can consume substantial CPU and RAM. If one runner executes multiple native builds simultaneously, each build can slow down and total memory can exceed limits.

Set concurrency according to the runner's total RAM/CPU. Consider a dedicated queue for native builds, larger runners, or capping concurrent native jobs.

### 11.2. Separate Dependency Caches from the Build Workspace

Maven/Gradle caches cut dependency download time, but they do not directly reduce the memory needed for reachability analysis or compilation. Ensure caches do not exhaust workspace/temp disk space.

Never share the same output/intermediate directory between two concurrent native builds unless the plugin/task explicitly supports it. Each job needs its own workspace.

### 11.3. Retain Diagnostic Artifacts in a Controlled Manner

You can archive:

- Native build logs.
- JSON build output.
- HTML Build Report if available.
- GraalVM/plugin/builder versions.
- Exit code and CI metadata.
- Heap dumps only when investigating, with restricted access.

Set appropriate retention policies because heap dumps, debug files, and reports can be large or contain sensitive information.

## 12. Example Pre-Retry Checklist

| Question | Result to record |
|---|---|
| Which phase did the build stop in? | Phase name and timestamp |
| Was there an `OutOfMemoryError`? | Yes/no, stack trace |
| Was the container `OOMKilled`? | State, exit reason, cgroup events |
| Current builder heap? | `-J-Xmx` |
| Container memory limit? | Limit and peak usage |
| CPU quota/throttling? | CPU limit, throttled periods |
| Enough disk/inodes? | `df -h`, `df -i` |
| Where is the temp directory? | Path, filesystem, and free space |
| Was the CI job timed out/canceled? | Job timeout, timestamp, and reason |
| Multiple concurrent native builds? | Runner concurrency |
| GraalVM and plugin versions? | Full versions |
| Actual build arguments? | Logs/config after profile resolution |

### Self-Check Questions

1. Why does a native executable's runtime memory not predict the memory required by the builder JVM?
2. How does `-J-Xmx` differ from `-Xmx`?
3. Why can a container be OOM-killed even when the builder JVM has not reached its maximum heap?
4. Is exit code 137 sufficient to conclude OOM?
5. When can reducing `--parallelism` make a build more stable?
6. Why does increasing the CI timeout not solve CPU throttling or a full disk?
7. Do Buildpacks and Native Build Tools accept build arguments in the same way?
8. Why should you save build logs, cgroup events, and the CI termination reason before retrying?

**Takeaway:** identify the exact limiting layer before changing configuration. `-J-Xmx` adjusts the builder JVM heap; container memory must accommodate native memory, thread stacks, and the compiler/linker; parallelism trades off duration against peak resource usage; timeouts only control job duration. Collect logs, exit reasons, cgroups, CPU, disk, and phase timings before retrying so you pick the right remediation.

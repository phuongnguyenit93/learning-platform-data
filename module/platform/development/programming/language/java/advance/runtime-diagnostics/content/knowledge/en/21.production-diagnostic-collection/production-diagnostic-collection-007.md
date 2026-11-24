# 21.7 Handling Attach Permission Limits, Read-Only Filesystems, or Environments Missing JDK Tools

## Learning Objectives

When running Java in containers, Kubernetes, distroless images, or hardened production environments, familiar collection steps such as `jcmd <pid> Thread.print`, `jcmd <pid> JFR.dump`, or taking a heap dump can fail due to **insufficient attach permissions**, **no writable path**, or **a runtime image lacking JDK tools**. Some environments hit all three barriers at once.

This lesson guides you to **diagnose each restriction separately and choose a safe collection method**, rather than blindly opening root privileges, disabling hardening, or restarting the application.

After this lesson, you will be able to:

- Distinguish errors across **PID/namespace**, **OS permissions**, **disabled attach**, **sockets/temp directories**, **tools missing from the image**, and **read-only filesystems**.
- Know what `jcmd` requires to work and why `jcmd -l` not seeing a JVM is **insufficient** to conclude the JVM is not running.
- Determine where a JFR file, heap dump, GC log, or fatal-error log is actually written by the **target JVM**; choose appropriate writable volumes and retention.
- Replace `jcmd` with **MXBeans/JMX** measurements, in-process thread snapshots, GC logs to stdout, startup-flag/API-initialized JFR, or JVM-supported thread-dump signals when appropriate.
- Understand the role, capabilities, and limits of **debug/ephemeral containers** in Kubernetes without automatically escalating privileges or weakening security.
- Design an evidence-collection runbook capturing timestamps, PID, JDK version, permissions, paths, and operational impact.
- Run a **Java 17+ self-observing JVM example using MXBeans** requiring no attach and writing no files.

**Scope:** VM flags and `jcmd` options illustrate HotSpot/OpenJDK Java 17+. Linux/container/Kubernetes is the primary operational context; the Java sample uses standard APIs and also runs on Windows. Tools, exact error wording, and attach mechanics vary by JDK vendor, OS, security policy, and container runtime. Do not generalize HotSpot diagnostics into guarantees for every JVM.

## 1. Three Distinct Barriers, Three Separate Questions

A "cannot collect diagnostics" failure must be classified before attempting fixes:

| Barrier | Typical Symptoms | Verification Questions | Initial Direction |
| --- | --- | --- | --- |
| **Attach** | `AttachNotSupportedException`, PID not visible, `Permission denied`, timeout waiting for attach listener | Is it the right process? Same host/PID namespace, effective UID/GID, and temp path? Did the JVM disable attach? | Fix context/permissions **proportionately**, or use attach-free capture |
| **Filesystem** | `Read-only file system`, `AccessDeniedException`, `No space left on device` when writing `.jfr`/`.hprof`/logs | Which directory is read-only? Is there a writable volume for the JVM user? Are space/inodes/quotas sufficient? | Use stdout or a writable volume, cap files, separate output paths from scratch space |
| **Missing JDK tools** | `jcmd: not found`, `jfr: not found`, missing `jstack` or `jmap` | Is the image JRE/jlink/distroless? Are binaries off PATH or omitted entirely? | Use MXBeans/JFR startup/logging; use a compatible debug image if policy permits |

These three barriers are **not equivalent**. For example:

- `jcmd` exists, wrong user → attach fails.
- Attach permissions exist, JVM launched with `-XX:+DisableAttachMechanism` → attach still fails.
- `jcmd` attaches cleanly, `JFR.dump` targets read-only `/app` → failure is at **the file output path**, not attach.
- Writable filesystem and permissions exist, image lacks `jcmd` → you cannot run an unpackaged binary.
- A read-only root filesystem **does not mean every mount is read-only**: `/tmp` or `/diagnostics` may be separate writable volumes.

**Rule:** record **the exact error message, process, UID/GID, mount, and timestamp**. Never jump from a filesystem error to assuming attach security must be disabled.

## 2. Decision Tree When Immediate Collection Is Needed

~~~text
Need evidence while the JVM is experiencing an issue
                    |
                    v
      Are suitable tools in the environment?
             /                    \
           Yes                    No
            |                       |
            v                       v
    Verify exact PID        MXBeans / app metrics,
    & tool context          GC stdout / JFR startup,
            |               thread-dump signal
            v               (if permitted)
     Attach succeeded?
       /           \
     Yes           No
      |              |
      v              v
  Choose low-     Classify:
  impact cmd      PID/UID/GID/namespace,
      |           attach disabled,
      v           temp path, container
  If cmd writes        |
  a file: writable     v
  mount exists?     Fix exact permission/
    /      \        config or fall back
  Yes      No
   |         |
   v         v
 Dump to   stdout/logs/
 valid     MXBeans/
 volume    planned JFR
   |
   v
 Verify file & integrity -> save evidence + timestamps
~~~

During a fast-moving incident, prioritize **already-available data**: application logs, metrics, tracing, GC logging, active JFR, container events, and restart history. Proceed to attach or heap dumps only after weighing benefit, impact, and operational authority.

## 3. What Does `jcmd` Require?

`jcmd` is a JDK diagnostic tool that sends commands to a running JVM. Per Oracle Java 21 documentation, it must run on the **same machine** as the target process with a matching **effective user/group identity**. Inside containers, namespaces, PID visibility, and access to the JVM's attach directory/socket also come into play.

### 3.1 Non-Intrusive Verification Steps

In a container/host with a shell and appropriate OS utilities:

~~~sh
# Identify the shell's current user:
id
id -u
id -g

# Inspect processes (if ps is present in the image):
ps -eo pid,uid,gid,args

# Check if tools are on PATH (if a shell exists):
command -v java
command -v jcmd

# If the JVM is PID 1 in the same namespace:
cat /proc/1/status
~~~

`/proc/1` is only an example for checking PID 1; **never assume every Java application runs as PID 1**. If the container lacks `sh`, `ps`, or `cat`, do not interpret "not found" as "no process running." Use orchestrator process metadata/metrics or an organization-approved debugging workflow.

In an environment with a JDK:

~~~sh
# List JVMs visible to the tool:
jcmd -l

# Use the verified real PID; the command below is very low impact:
jcmd 1234 VM.version

# List commands supported by this JVM:
jcmd 1234 help
~~~

`1234` is an illustrative PID only. **Never run `jcmd 0 ...` while investigating a single service**, because per `jcmd` syntax, PID 0 can dispatch the command to **all visible JVMs**. Similarly, matching by main-class instead of PID can hit multiple processes; a verified real PID is safer.

Specifically, `jcmd -l` documentation notes exceptions for JVMs running in separate Docker processes. If the list is empty, look up the PID via appropriate metadata/process views instead of assuming the JVM is dead.

### 3.2 Why Attach Fails

**Wrong user:** the app runs under UID 10001 while the debug/host shell runs under another UID. Being "root inside a debug container" does not automatically mean interacting with a non-root JVM in another namespace/security context will succeed. Verify effective UID/GID and OS policies against the real JVM.

**Wrong PID namespace / host context:** PID 1 inside a container may map to a different PID on the node. A helper that cannot see the target process namespace cannot attach, even with `jcmd` installed.

**Attach mechanism disabled:** HotSpot supports launching with:

~~~sh
java -XX:+DisableAttachMechanism -jar app.jar
~~~

This is a **JVM flag** and must precede `-jar`. In testing on HotSpot JDK 24, running `jcmd <pid> VM.version` against a JVM with this flag returned `AttachNotSupportedException: The VM does not support the attach mechanism`. Swapping `jcmd` for `jstack`/`jmap` normally fails too, since those tools also rely on the Attach API. Never assume you can "re-enable" attach in a running JVM via `jcmd`.

**Temp/socket unavailable:** on HotSpot/Linux, attach can use special files/sockets tied to the PID and temporary directory (such as `/tmp/.java_pid<PID>`), subject to mount namespaces, UIDs, and permissions. A read-only or full `/tmp` can prevent attach from completing. **Never manually create, `chmod` broadly, or delete sockets inside `/tmp` belonging to a live JVM** to try your luck: you risk disrupting or interfering with another process's state.

**Unresponsive attach listener:** an overloaded or hung JVM can cause commands to time out. Distinguish this from a dead JVM, reused PID, wrong namespace, or security policies blocking signals/sockets.

**Additional OS privileges:** container security policies, user namespaces, `/proc` visibility, seccomp, AppArmor/SELinux, and mount layouts can affect tools. Never assume adding `CAP_SYS_PTRACE`, running privileged, or running as root is a standard requirement for `jcmd`; grant only truly necessary permissions after confirming the mechanism and obtaining approval.

### 3.3 Avoid Unverified "Tricks"

- `-Djava.io.tmpdir=/somewhere` is **not guaranteed** to fix attach. Socket/attach behavior is implementation-specific and may not follow every Java application temp property.
- `-Djdk.attach.allowAttachSelf=true` applies to a JVM attaching to itself in specific scenarios; it **does not replace** user/PID/namespace requirements for an external tool process.
- `-XX:+StartAttachListener` may initialize the listener early on supporting HotSpot builds, yet cannot override `-XX:+DisableAttachMechanism`, file permissions, or security contexts. Check option support and test in staging.
- Running tools from a newer or different-vendor JDK is **not always compatible** with the target JVM; match version/vendor where possible and verify with `help`.
- Never set `/tmp` or sensitive mounts to mode `777`, disable seccomp/AppArmor, or deploy privileged containers merely to make a command run.

If policy intentionally disables attach, choose an **attach-free** collection path instead of trying to bypass policy.

## 4. Read-Only Filesystems: Pinpoint Exactly Where Writes Are Blocked

In containers with `readOnlyRootFilesystem: true`, the image's root filesystem is protected from writes, while **writable volume mounts** can still be provided. The question is not "can the JVM write anywhere," but which paths are mounted, which user owns them, and which ones have free space.

### 4.1 Inspecting Locations and Capacity

On Linux with a shell and utilities:

~~~sh
# Relevant mounts, directory permissions, and capacity:
ls -ld /tmp /diagnostics
df -h /tmp /diagnostics
df -i /tmp /diagnostics
cat /proc/mounts
~~~

These commands may be absent in distroless images. Inspect `/proc/mounts` to distinguish read-only (`ro`) from writable (`rw`) mounts when readable. `df -h` checks bytes and `df -i` checks inodes; running out of either prevents file creation.

**Test writes** only in a designated diagnostics directory, never touching source, config, or sensitive folders:

~~~sh
# Run only when /diagnostics is an authorized area and mktemp exists:
tmpfile=$(mktemp /diagnostics/probe.XXXXXX) || exit 1
rm -- "$tmpfile"
~~~

`mktemp` syntax varies between GNU and BusyBox; on images without a shell or tools, verify mounts through other approved mechanisms. `test -w` or `Files.isWritable(...)` can be predictive only; **creating an actual test file on the exact mount** provides stronger proof when permitted.

### 4.2 Distinguishing Four Path Categories

| Path Category | Who Uses It | Risk When Read-Only / Over Quota |
| --- | --- | --- |
| **Application / `user.dir`** | Relative file paths, app config/cache/logs | A relative `filename=...` may try writing into read-only `/app` |
| **JVM temporary area** | Certain temp files, VM/attach mechanics per OS/JDK | Read-only or mispermissioned `/tmp` can break diagnostics |
| **JFR repository** | Temporary chunks while JFR records to disk | Non-writable repo prevents JFR from recording/dumping as expected |
| **Final output** | `.jfr`, `.hprof`, `hs_err_pid...log`, and log files | Requires writable path, enough space, and data-protection permissions |

A valid `filename=/diagnostics/capture.jfr` **does not prove JFR's temporary repository is writable**. On HotSpot Java 17+, configure the JFR repository location via `-XX:FlightRecorderOptions=repository=...` alongside the final output path.

### 4.3 When a Heap Dump Is Needed

If the JVM encounters heap OOM and you need a post-incident dump, prepare ahead of time:

~~~sh
java -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/diagnostics \
     -XX:ErrorFile=/diagnostics/hs_err_pid%p.log \
     -jar app.jar
~~~

This is an example command for a **fresh launch**, requiring `/diagnostics` to exist and be writable. Heap dumps can be **huge**, impact timing, and contain sensitive data; enforce disk budgets and access/retention/deletion policies. A JVM killed by **container cgroup OOMKill** or `SIGKILL` does not always get a chance to write a heap dump or fatal-error log; never cite the absence of a file as proof against memory issues.

`-XX:ErrorFile` is for **fatal JVM errors** when HotSpot can emit a report, not a catch-all log for ordinary Java exceptions. Never confuse fatal-error logs with heap dumps or GC logs.

## 5. Nowhere to Write Files: Prefer `stdout`/`stderr` and Existing Telemetry

Containers commonly collect `stdout`/`stderr` via logging drivers or orchestrators. When the filesystem is read-only while console streams work, **Unified Logging** captures GC, safepoint, and JVM startup data without creating files inside the image:

~~~sh
# Run from JVM startup; requires no jcmd:
java '-Xlog:gc*:stdout:time,uptime,level,tags' -jar app.jar
~~~

This syntax was verified on HotSpot JDK 24 (succeeding alongside `-XX:+DisableAttachMechanism`). Choose the minimal tags/levels needed for your question. `gc*` emits considerable detail, especially at startup; for cost-sensitive or high-volume systems, start with `-Xlog:gc=info:stdout:uptime,level,tags` and increase detail only as needed.

A narrower stdout example:

~~~sh
java '-Xlog:gc=info:stdout:uptime,level,tags' -jar app.jar
~~~

**Pros:** requires no app-owned file write permissions, logs carry timestamps, and collectors ship them off-container (if the pipeline is configured properly). **Limits:** logs do not replace heap dumps or JFR, can be dropped if collectors lag or retention is short, and logging cost still applies. If an already-running app lacks logging, you cannot "inject JVM startup flags" into that live process without a new restart/deploy.

### 5.1 Taking a Thread Dump Without the Attach API (Conditionally)

On HotSpot/Linux, when holding **permission to send signals** to the target process:

~~~sh
# Verify the PID first; this is QUIT, not TERM or KILL.
kill -QUIT 1234
~~~

Normally HotSpot handles `SIGQUIT` by **printing a thread dump** to the **target JVM's output** and continuing execution. This is distinct from attach: no `jcmd` is needed, though OS signal permissions and policies still apply. **Never confuse `kill -QUIT` with `kill -9`, `SIGTERM`, or `SIGABRT`**. Check the JVM's `stdout`/`stderr` (such as orchestrator logs)—do not expect the dump to appear in the terminal that sent the signal.

Limitations:

- `-Xrs` can disable the `SIGQUIT`-based thread dump handler; signal handling can also differ across JVMs and platforms.
- Requires the right PID namespace or process targeting and signal permissions for the sending user.
- Thread dumps can reveal thread names, methods, and sensitive stack context; restrict sharing.
- Signals do not provide heap histograms, NMT, or full JFR; avoid spamming signals and creating noise.
- On Windows, **Ctrl+Break** is an option when the app has an attached console/handler; never apply Linux `kill -QUIT` examples directly on Windows.

### 5.2 Leverage Logs and Metrics Even When the Process Is Unresponsive

Even without attach, previously enabled sources may still exist:

- **Application metrics / health endpoints:** latency, request rate, errors, and heap/GC/thread/classloading via metrics bridges.
- **Orchestrator logs/events:** container restarts, exit codes, `OOMKilled`, probe failures, cgroup limits, pod/node pressure, and timestamps.
- **Integrated OpenTelemetry/APM/tracing:** spans, error attributes, deployment versions.
- **Host/container OS metrics:** RSS, CPU, file descriptors, cgroup memory usage, I/O; distinguish OS metrics from JMX heap used.
- **Startup-enabled JFR** exported per schedule; analyzable offline on another machine.

Select evidence sources by question rather than grabbing everything. Lacking a heap dump does not prevent initial timeout triage; GC logs, thread metrics, and request timelines are often enough to narrow the cause.

## 6. No `jcmd` in the Image: Understand What the Runtime Actually Contains

In a full JDK build, `java`, `javac`, `jcmd`, and `jfr` are separate binaries; a **runtime image** slimmed down with `jlink` might contain only `java` and the modules needed to run the app. A distroless image may lack a shell, package manager, `ps`, and `jcmd` altogether. **Having `java` does not prove all JDK tools are present.**

If you can run commands:

~~~sh
java -version
java --list-modules
command -v jcmd
command -v jfr
command -v jstack
~~~

`java --list-modules` checks for modules such as `java.management`, `jdk.jfr`, and `jdk.management.jfr` (if present). **Missing the `jcmd` binary does not mean `jdk.jfr` is absent**, and having `jdk.jfr` does not mean the `jfr` CLI tool is installed or write permissions exist. Verify each capability individually.

### 6.1 Valid Options When Tools Are Missing

1. **Leave the image unchanged:** use logs, built-in JMX/MXBeans, in-process diagnostics, and startup JFR if supported by modules; write files to a writable mount.
2. **Use a full-JDK image in staging:** replay the workload under a full JDK image with matching vendor/version, GC, flags, and key constraints. Remember this is a new test run, not live data from the production process.
3. **Build a controlled debug deployment:** via operational release workflows, include needed tools in an authorized image/environment; never `apt-get`/`apk add` packages directly into immutable production containers.
4. **Ephemeral debug containers** (Kubernetes): provide a shell and JDK tools for investigation **when policy permits**, while verifying PID, effective user/group, mounts/attach sockets, and version. Having tools in a sidecar **does not guarantee** attach to another app container.
5. **Secured remote management APIs:** JMX/`FlightRecorderMXBean` when supported by modules and protected with authentication and TLS; never open unauthenticated ports across the network for a few metrics.

**Do not treat `jhsdb` as a "guaranteed fallback for `jcmd`."** Serviceability Agent/`ptrace` requires OS privileges, can pause or impact the process, and imposes strict compatibility requirements. Use it only when lighter methods fail, with operator approval and clear awareness of risk.

## 7. Java 17+ Practice: In-Process MXBean Collection Without Attach or Files

If you can add code to the application or run diagnostic logic **inside the exact JVM under observation**, `java.lang.management` provides rich metrics without `jcmd`, JNI, or filesystem access. The example below uses:

- `MemoryMXBean` to read `getHeapMemoryUsage().getUsed()`.
- `ThreadMXBean` to read thread count and a thread snapshot via `dumpAllThreads(false, false)`.
- `ClassLoadingMXBean` to inspect loaded class counts.

The code prints stable **assertion checks** instead of hard-coding thread counts, heap bytes, or class counts that vary across JVMs. In real applications, emit concrete measurements to a **secured metrics endpoint or `stdout`** per observability policy.

Save under the exact name **NoAttachSnapshot.java**:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public final class NoAttachSnapshot {
    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        ClassLoadingMXBean classes = ManagementFactory.getClassLoadingMXBean();

        long heapUsed = memory.getHeapMemoryUsage().getUsed();
        int threadCount = threads.getThreadCount();
        int loadedCount = classes.getLoadedClassCount();
        ThreadInfo[] snapshot = threads.dumpAllThreads(false, false);

        System.out.println("HEAP_USED_NONNEGATIVE=" + (heapUsed >= 0));
        System.out.println("THREAD_COUNT_POSITIVE=" + (threadCount > 0));
        System.out.println("LOADED_CLASSES_POSITIVE=" + (loadedCount > 0));
        System.out.println("THREAD_SNAPSHOT_NONEMPTY=" + (snapshot.length > 0));
        System.out.println("NO_JCMD_REQUIRED");
    }
}
~~~

Compile and run (in a build environment with JDK 17+):

~~~sh
javac --release 17 NoAttachSnapshot.java
java NoAttachSnapshot
~~~

**Exact stdout** from a verification run on HotSpot JDK 24:

~~~text
HEAP_USED_NONNEGATIVE=true
THREAD_COUNT_POSITIVE=true
LOADED_CLASSES_POSITIVE=true
THREAD_SNAPSHOT_NONEMPTY=true
NO_JCMD_REQUIRED
~~~

You can even **disable attach at startup** and the program still runs normally:

~~~sh
java -XX:+DisableAttachMechanism NoAttachSnapshot
~~~

This code **does not invoke** `jcmd`, does not use the Attach API, and creates no files. It simply verifies observable values—**not a profiler sufficient to diagnose a memory leak**. In production, read and export real values (heap used/committed, thread states, loaded classes) via an authenticated endpoint or metrics pipeline; `dumpAllThreads(false, false)` can be costly with very high thread counts, so never poll it continuously at high frequency.

**Environment note:** the app requires the `java.management` module; in a minimal `jlink` runtime image lacking that module, it will not run until rebuilt with it. You cannot read **another production process's data** by launching `NoAttachSnapshot` as a separate process: each JVM reads **only its own** metrics. It must be built into the target JVM upfront or exposed via an authorized agent/management mechanism.

### 7.1 Purpose-Built Usage Example Inside a Service

If the service already exposes metrics, you can add measurements like:

~~~java
long heapUsed = ManagementFactory.getMemoryMXBean()
        .getHeapMemoryUsage().getUsed();
int threads = ManagementFactory.getThreadMXBean().getThreadCount();
~~~

This is a **Java snippet**, not a standalone program. Ship these values via your metrics system tagged with JVM start time, instance ID, pod, and deployment version. Never stuff thread dumps or full stack traces into metric labels: doing so is both sensitive and causes extreme cardinality explosion.

## 8. Capturing JFR From Startup When Attach Is Prohibited

JFR can run **without `jcmd`** when enabled via JVM flags at launch and supported by the runtime modules. Two writable path layers are then required:

1. **Temporary repository** holding JFR chunks when recording to disk.
2. **Final filename** exported when the recording stops or dumps.

HotSpot JDK 17+ example when `/diagnostics/jfr-repo` and `/diagnostics` are writable:

~~~sh
java \
  -XX:FlightRecorderOptions=repository=/diagnostics/jfr-repo \
  -XX:StartFlightRecording=settings=default,filename=/diagnostics/incident.jfr,dumponexit=true,maxsize=32m \
  -jar app.jar
~~~

- `settings=default` selects a profile suited for relatively long observation; no need to enable every event.
- `maxsize=32m` caps **data retained in the recording**; files and repositories still need real disk capacity and overhead headroom, so do not treat 32 MiB as a hard cap on all files.
- `dumponexit=true` requests export when the JVM **shuts down gracefully enough to handle it**; processes hit by `SIGKILL` or cgroup OOM kills may not dump in time.
- To retrieve recordings **while the process is still running**, design a pre-approved control path (such as `jdk.jfr.Recording` inside the app, a secured management API, or permitted attach). Do not expect `dumponexit` to write a new file whenever latency spikes.
- `incident.jfr` lives on the filesystem **seen by the JVM**, not automatically on the `kubectl` terminal or operator workstation.
- Account for permissions, mount durability, and capture timing; deleting a container can wipe files on `emptyDir`.

A local experiment on HotSpot JDK 24 launched a JVM with both `-XX:FlightRecorderOptions=repository=...` and `-XX:StartFlightRecording=...`, produced a `.jfr` file, and read it with `jfr summary`. That confirms syntax/mode in a JDK environment; it **does not prove every read-only image will succeed** if mounts or modules differ.

### 8.1 Missing `jfr` in the Image Still Allows Reading Elsewhere

After copying the recording to an analysis environment with a compatible JDK and proper access controls, run:

~~~sh
jfr summary incident.jfr
jfr print --events jdk.GarbageCollection incident.jfr
~~~

Or open it in JDK Mission Control. Inspect actual metadata and event types in the analysis environment; lacking the `jfr` CLI inside the runtime image is **no reason to skip capture** if the VM can write the file. Never confuse `.jfr` with `.jfc`: `.jfc` files are only configuration templates.

### 8.2 JFR and Immutable Disks

A read-only root filesystem with a separate writable mount for the repository can still run JFR. Conversely, if every writable location available to the JVM is locked down, **never assume disk-based JFR recording or file dumps will work**. Some setups can stream or buffer events in memory inside the process, yet availability and retrieval depend on JDK version and integration; never treat `disk=false` as a "guaranteed way to produce `.jfr` files without a filesystem."

If no writable mount can be provided, prioritize **existing metrics/JMX, `stdout`/`stderr` logging, in-process thread snapshots**, and authorized external tooling. Postmortem JFR capability should be designed into the deployment from the start.

## 9. Kubernetes Pattern: Read-Only Root With Dedicated Writable Diagnostics

Below is an **illustrative YAML snippet** inside a Pod template, not a complete Deployment:

~~~yaml
spec:
  securityContext:
    fsGroup: 10001
  containers:
    - name: app
      image: example/java-service:1.0
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        readOnlyRootFilesystem: true
      volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: diagnostics
          mountPath: /diagnostics
  volumes:
    - name: tmp
      emptyDir:
        sizeLimit: 128Mi
    - name: diagnostics
      emptyDir:
        sizeLimit: 1Gi
~~~

This design **keeps the root filesystem read-only** while mounting `/tmp` and `/diagnostics` separately. Adapt it for PodSecurity policies, storage classes/permissions, UID/GID, node resources, and retention needs. `fsGroup` **does not guarantee every volume driver/permission scenario works**; verify write access under the JVM process's effective user.

**Important notes on `emptyDir`:**

- Data is tied to the Pod lifecycle, not durable once the Pod is deleted; extract files to approved storage before losing the Pod.
- `emptyDir.sizeLimit` is a storage cap, not a guarantee that the node has free space or IOPS.
- Using `emptyDir.medium: Memory` charges data against node/container memory per Kubernetes rules; avoid arbitrary tmpfs for large heap dumps.
- Volume mounts may be restricted by policy; verify the actual deployed configuration rather than assuming from intended YAML.

`.hprof`, `.jfr`, and `hs_err_pid...log` files can hold sensitive data. Copy them only to locations with appropriate ACLs and retention, log an audit trail, and delete per policy once the investigation concludes.

### 9.1 Extracting JFR Files After Capture

Once the service writes to `/diagnostics` and organizational policy permits:

~~~sh
# Conceptual example; substitute actual namespace/pod/container/path:
kubectl cp -n team payments-0:/diagnostics/incident.jfr ./incident.jfr -c app
~~~

`kubectl cp` may require `tar` inside the container; distroless/minimal images often **lack `tar`**, causing the command to fail even when the file exists. Never assume the file is missing. Use an operationally approved extraction path (volume extraction, app/sidecar storage upload, or `kubectl exec -- cat` if the container actually has binaries and policy allows). Choose a method that verifies checksums/file sizes and never leaks sensitive data to public logs.

## 10. Debug/Ephemeral Containers With JDK Tools: Useful, Not Magic

When the application image lacks a shell or `jcmd`, Kubernetes supports temporary debug containers:

~~~sh
# Illustrative command; the JDK image must be organization-approved:
kubectl debug -n team -it pod/payments-0 \
  --image=example/approved-jdk-tools:21 \
  --target=app -- sh
~~~

This creates an ephemeral container targeting `app`, though visibility into the target container's processes depends on container runtime support and policy. Kubernetes documents that if processes are not visible, the runtime may not support process namespace targeting.

Even once a PID is visible:

- **PID namespace:** the tool may see the process, yet its PID in that context may differ from JVM expectations; verify via `ps`/`/proc`.
- **Effective user/group:** the debug container may run a different UID from the app; never escalate privileges blindly to force attach.
- **Filesystem/mount namespace:** the debug container has its own image and mounts. The app's `/tmp` and attach socket may **not** appear at the same path; real attach must satisfy that JVM's attach mechanism.
- **JDK version/vendor:** choose matching binaries for the target JVM whenever possible.
- **Security policy:** PodSecurity/OPA/RBAC/Admission may forbid or constrain ephemeral containers. Cluster permission to launch debug containers is a privileged capability.
- **Output paths:** running `jcmd ... JFR.dump filename=...` requires the **target JVM** to be able to write that path; the file is not automatically written into the ephemeral container's filesystem.

**Never turn every incident into a privileged Pod or `--profile=sysadmin`.** Those options carry heavy security impact and do not automatically fix namespace/temp/socket mismatches. Use elevated profiles/permissions only via formal approval with narrow scope, audit logging, and strict time limits.

## 11. Error → Diagnosis → Remediation Table

| Symptom | Common Problem Class | Safe Verification | Least-Invasive Remedy |
| --- | --- | --- | --- |
| `jcmd: command not found` | Tool not packaged / missing from PATH | Check image/JDK runtime and `command -v` if shell exists | MXBeans/logging/startup JFR; approved debug tooling |
| `jcmd -l` shows no JVM | PID namespace/container visibility or JVM not running | Check process metadata, `/proc`, orchestrator | Use context-accurate PID; never broadcast via PID 0 |
| `AttachNotSupportedException` | Attach disabled or unreachable | Check startup flags, permissions, PID, and JVM state | Do not bypass; use in-process metrics or startup capture |
| `Permission denied` on attach | Wrong UID/GID, security policy, or mount | Compare effective identities, process owner, policy | Run under authorized identity; never default to root/privileged |
| Attach timeout | Unresponsive JVM, temp/socket error, process mismatch | Check timestamps, JVM liveness, `/tmp`, load | Collect stdout/OS metrics/SIGQUIT if permitted; avoid tight attach retries |
| `Read-only file system` on dump | Output path or JFR repository is read-only | Inspect real mounts and JVM user, test scoped file | Switch to writable volume/stdout; configure paths at deploy |
| `No space left on device` | Disk/inodes/quota exhausted | `df -h`, `df -i`, volume usage | Halt large dumps, reduce retention/move data per policy |
| `JFR.dump` fails to write despite OK attach | Target JVM lacks path permissions | Check the **target JVM's** filesystem | Choose a writable output visible to the target |
| No `.hprof` after OOMKill | Process killed before Java could handle it | Inspect Pod/container termination reason and logs | Rely on pre-OOM JFR/metrics; improve observability next deploy |
| `jfr: not found` yet `.jfr` exists | Missing **analysis tool**, not a data failure | Check file size and magic/read with compatible external JDK | Copy to secure analysis host; run `jfr summary`/JMC |
| No file after `dumponexit=true` | Unclean shutdown, wrong path, read-only/quota | Check VM exit mode, output/repository, flags | Export snapshots via API/management before process loss |
| `kill -QUIT` yields no dump | Wrong PID/permissions, `-Xrs`, or custom signal handling | Check JVM flags and target process logs | Use MXBeans/in-process debug or other approved method |

All rows above represent **possibilities**, not rigid "one error always has one cause" rules. In particular, `jcmd` error messages depend on JDK/OS: record verbatim messages with version info.

## 12. Three Operational Scenarios: Choosing a Collection Strategy

### Scenario A — Distroless, JVM Healthy Except for Latency Spikes

**Context:** app container lacks `sh`, `jcmd`, and `jfr`, root filesystem is read-only; request latency metrics, GC logs, and app metrics are already available.

**Approach:**

1. Collect timelines of request p99, CPU, GC pauses, container throttling, and existing heap/thread metrics.
2. Do not repeatedly retry `kubectl exec -- sh` when no shell exists; inspect the deployment image.
3. If thread states are needed, integrate an authenticated diagnostic endpoint using `ThreadMXBean.dumpAllThreads(...)` with rate limiting; or redeploy in a maintenance window with startup JFR + a writable volume.
4. When reproducing, take multiple timestamped snapshots; compare thread stacks across the same request window rather than relying on one instant.
5. Preserve hardening and auditing; never open unprotected JDWP/JMX.

**Conclusion:** lacking JDK tools inside the image does not block observation via app/OS metrics; redeploying to enable deeper evidence should be a controlled decision.

### Scenario B — `jcmd` Present, Attach Locked Down by Policy

**Context:** image includes `jcmd`, PID is right, UID matches, yet the JVM started with `-XX:+DisableAttachMechanism`.

**Approach:**

1. Record the error text, launch arguments, and policy: this may be intentional hardening, **not a random bug**.
2. Rely on console logs, existing startup JFR, and properly managed metrics/JMX.
3. If policy must change, request approval and update JVM startup flags in the next release; never rely on runtime attach to "turn it back on."
4. Once authorized, test `jcmd <pid> VM.version` in staging before attempting higher-impact commands.

**Conclusion:** the goal is preserving evidence without breaking security boundaries—not forcing `jcmd` to work at any cost.

### Scenario C — Attach Succeeds, Cannot Write Heap Dump / JFR

**Context:** `jcmd <pid> Thread.print` succeeds, while `jcmd <pid> GC.heap_dump ...`/`JFR.dump` fails with read-only or out-of-disk errors.

**Approach:**

1. Classify this as an **I/O output path** issue, not an attach failure.
2. Check mounts, UID/GID, and quotas inside the **target JVM's filesystem**; locate an approved writable volume.
3. If no writable space exists, prioritize `Thread.print` stdout responses, metrics, and stdout GC logs; never cram a heap dump into `/tmp` just because a tiny bit of space is free.
4. Plan a volume with secure capacity/retention, and throttle or pause large-file commands.
5. On the next deploy, configure `HeapDumpPath`, `ErrorFile`, and JFR repository/output properly from startup.

**Conclusion:** not every command needs a file (`Thread.print` returns text), whereas large artifacts require permissions, disk space, and a storage plan.

## 13. Auditable Evidence-Collection Runbook

A simple sheet so other investigators can reproduce and cross-check:

~~~text
Incident ID / UTC timestamp / timezone:
Namespace, Pod, container, node (if applicable):
JVM PID in which namespace / JVM start time:
Java vendor/version, GC, relevant flags:
Image/runtime (full JDK, jlink, distroless):
Target JVM effective UID/GID:
Host/container and UID/GID where tool was invoked:
Verbatim command and output/error:
Attach: enabled/disabled/unknown; VM.version result if attempted:
Mounts (/tmp, JFR repository, output folder): rw/ro and owner:
Disk space / inodes / quota:
Collected data sources: logs, JMX, JFR, threads, OS metrics:
Artifact storage path, checksum, access controls, retention:
Impact on latency/CPU/disk and capture duration:
Limitations and data still missing:
Next hypothesis / falsification criteria:
~~~

**Prioritize collection in ascending order of impact:**

1. Existing logs, metrics, and events; preserve timestamps and versions.
2. MXBeans/app endpoints and `jcmd VM.version`/`Thread.print` (if attach works).
3. Duration- and size-bounded JFR `profile`, targeted GC/safepoint logs; watch overhead.
4. Heap dumps or deeper diagnostics only when object/retention proof is needed and impact, capacity, and sensitive data are approved.
5. Post-mortem core/SA debugging is a special-case choice, never a default step.

Avoid changing multiple factors at once (root privileges, JVM flags, image, pod placement, collector): if the issue disappears, you will not know what actually fixed it. For post-incident investigation, **do not restart prematurely** and wipe uncollected evidence unless restoring service is a clear operational/safety priority.

## 14. Common Mistakes

1. **"`jcmd -l` is empty, so no JVM is running."** May be due to container/PID visibility or permissions.
2. **"Having `java` guarantees having `jcmd`."** Minimal runtime images often strip tools.
3. **"Running as root or privileged always fixes attach."** Namespace, socket, policy, or compatibility mismatches can still fail, and escalating privileges adds risk.
4. **"Disable `DisableAttachMechanism` at runtime with `jcmd`."** The attach mechanism itself was disabled at startup.
5. **"`-Djava.io.tmpdir` always fixes attach."** Attach implementations have their own socket/temp rules; verify against the exact JVM/JDK.
6. **"Read-only root filesystem means every mount is read-only."** Writable volumes can exist when configured.
7. **"`JFR.dump filename=...` writes to the caller's machine."** The file is written by the target JVM on the filesystem it sees.
8. **"Writable `filename` guarantees a writable JFR repository."** Final output and scratch/repository are two separate paths.
9. **"`dumponexit=true` guarantees a dump after `SIGKILL`/OOMKill."** Forced kills can prevent the JVM from writing dumps.
10. **"Without JDK tools, expose remote JMX/JDWP publicly."** Use metrics/startup JFR; debug ports must always be protected.
11. **"A debug container with `jcmd` has a 100% attach success rate."** Still requires matching PID/mount/user/security and JVM compatibility.
12. **"`emptyDir` is durable long-term storage."** Data disappears when the Pod is deleted; export properly.
13. **"`kill -QUIT` is the same as `kill -9`."** They are different signals; on HotSpot/Linux, `SIGQUIT` normally prints a thread dump without killing the app.
14. **"No heap dump captured means no heap leak."** A missing artifact proves nothing about root cause.
15. **"Capturing a snapshot guarantees enough data to diagnose."** Must correlate workload, timestamps, retained data, and representativeness.
16. **"No need to protect JFR/heap dumps since they are just diagnostics."** They can contain internal and sensitive data.

## 15. Practice Exercises With Solutions

**Exercise A.** You use a distroless image; `kubectl exec ... -- jcmd` reports the executable does not exist. The service still exports GC/thread metrics. What should you do first?

**Solution:** Rely on existing metrics/logs and classify the issue as missing tools in the image; do not escalate privileges or swap containers just hunting for a nonexistent binary. If evidence is lacking, plan an approved debug image or startup JFR + writable volume.

**Exercise B.** JVM PID 1 runs as UID 10001. `jcmd` in a debug sidecar runs as UID 0, sees PID 1, yet attach fails. Can you conclude the JVM is broken?

**Solution:** Not yet. Check effective UID/GID, namespaces, `/tmp`/socket mounts, security policies, JDK compatibility, and startup attach flags. PID visibility is only one condition. Running privileged is not the default remedy.

**Exercise C.** `jcmd 1234 Thread.print` returns stacks, while `JFR.dump filename=/app/problem.jfr` fails with `Read-only file system`. Do you need to fix attach?

**Solution:** No. Attach already succeeded. Point the output path to a mount writable by the **target JVM**, ensuring repository/output paths and space suffice; or fall back to stdout/metrics if no suitable volume exists.

**Exercise D.** `-XX:+HeapDumpOnOutOfMemoryError` is set, yet the Pod terminates with `OOMKilled` and no `.hprof` exists. Can you state no Java memory issue occurred?

**Solution:** No. A cgroup OOM kill can terminate the process before the JVM detects a Java `OutOfMemoryError` and writes a dump. Correlate cgroup memory, OS RSS, heap metrics/GC logs, and startup recordings if present.

**Exercise E.** A JVM launches with `-XX:+DisableAttachMechanism`, while `NoAttachSnapshot` still prints `NO_JCMD_REQUIRED`. Is that a contradiction?

**Solution:** No. MXBeans run **inside** the JVM and do not need the external Attach API. Its metrics do not automatically represent other JVMs.

**Exercise F.** A debug container has the `jfr` command, whereas the app lacks the JFR module and has no `.jfr` file. Can the external `jfr` command "start recording" inside the app?

**Solution:** No. `jfr` is a tool for managing/reading recording files; it cannot substitute for JFR support in the **target runtime** or generate events the JVM does not support. Recording requires a JVM with JFR and a valid startup/control mechanism.

**Exercise G.** Every writable path in the image is locked down, yet the system has `-Xlog:gc=info:stdout:...` configured. Can you still collect GC logs?

**Solution:** Yes, provided HotSpot supports the flag and the logging pipeline captures `stdout`. Data flows over the stream without needing the app to write GC log files onto the root filesystem—though the pipeline must have sufficient retention/quota and drop no logs.

**Exercise H.** An SRE sends `kill -QUIT` on Linux to a JVM running with `-Xrs` and sees no thread dump. Should they keep spamming the signal to "force" it?

**Solution:** No. `-Xrs` can disable the `SIGQUIT` handler; inspect JVM flags and OS policy, then switch to planned MXBeans/metrics/JFR. Repeated signals do not grant new permissions or capabilities.

## 16. Remember Through Three Questions

1. **Why did attach fail?** Check PID, namespace, effective UID/GID, attach flags, temp/socket, JVM responsiveness, and policy; never default to root.
2. **Where are writes blocked?** Separate read-only root, mounts, JFR repository, output files, disk/inodes, and JVM user; prefer `stdout` or secured volumes.
3. **What remains without JDK tools?** Use in-process MXBeans, secured app/JMX metrics, startup/API JFR if present, GC stdout, OS/orchestrator evidence, and approved debug containers.

**The operational goal is not "make every command work," but "capture the right evidence with minimal privilege, acceptable impact, and clear verifiability."**

### Official References

- Oracle Java 21, `The jcmd Command`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java 21, `The java Command` (`-Xlog`, `-XX:StartFlightRecording`, `-XX:FlightRecorderOptions`, heap/fatal logs): https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle Java 21, `Diagnostic Tools`: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle Java 21, `Prepare Java for Troubleshooting`: https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html
- Oracle Java 21, `Flight Recorder Configurations`: https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html
- Oracle Java 21 API, `ThreadMXBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle Java 21 API, `MemoryMXBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html
- Kubernetes, `kubectl debug`: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_debug/
- Kubernetes, `Debug Running Pods`: https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/

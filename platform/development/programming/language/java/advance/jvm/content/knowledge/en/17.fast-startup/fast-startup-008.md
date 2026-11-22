# Measuring Readiness Time and Memory Footprint to Evaluate Startup Gains

## 1. What Does Fast Startup Improve?

Optimizing Java startup is not simply about making the `public static void main` line execute a few milliseconds earlier. A service may print "Started" without having opened its port yet, may have opened its port without having loaded its configuration yet, or may accept connections without successfully serving actual requests yet. Similarly, reducing heap used does not necessarily reduce **actual RAM** or the memory limit needed for a container.

To evaluate the startup gains of a Java 17 application, at least three questions must be answered:

1. **How long does it take for the application to actually be ready to serve?** Measure from a point outside the JVM to a business-meaningful **readiness condition**, not just to an arbitrary log line.
2. **How much memory does the application use at that point and after stabilizing?** Distinguish **heap used**, **heap committed**, **non-heap/metaspace**, **native memory**, **RSS**, cgroup limits, and peak.
3. **What is the trade-off?** Faster startup may reduce steady-state throughput, increase GC, increase RSS, make containers more prone to OOMKilled, or worsen first-request latency.

This article focuses on **empirical measurement and evaluation** for HotSpot/OpenJDK Java 17: defining the readiness point, creating a baseline, running multiple process iterations, collecting timing and memory metrics, making controlled comparisons, finding sources of variance, and making decisions based on deployment goals. Standalone examples use **Java 17**, JDK tools `java`, `javac`, `jcmd`, `jstat`, and OS tools when needed.

**Distinction:** Java SE guarantees Java behavior at the language/JVM level, and does not standardize a unified "startup time" metric for all applications. Options such as CDS, compiler tiers, GC, and Native Memory Tracking are **mechanisms dependent on the JVM/JDK build**. Hypothetical timing/RSS numbers used in examples are clearly labeled and are not presented as measured data.

## 2. Time Milestones: Process Started Differs from Application Ready

A useful timeline:

```text
T0             T1                 T2                  T3                T4
|--------------|------------------|-------------------|-----------------|
Launcher       JVM initialized    Framework/app       Socket opened     Endpoint /ready
process begins                    initialization                        returns success
                                                                        + dependencies OK

T5: first business request actually completes successfully
T6: throughput/latency after warm-up reaches steady-state condition

T0→T4: startup to readiness (often an important operational target)
T0→T5: first-successful-request latency
T4→T6: warm-up time after ready, if any
```

The milestones are a model; the actual process may differ in order or run partially in parallel.

Endpoints that are commonly conflated:

- **Process created:** the OS creates the Java process; does not prove the JVM/app is ready.
- **`main` entered:** the JVM has loaded/initialized the classes needed to invoke `main`; many frameworks/dependencies have not completed yet.
- **Application init complete:** a callback/framework event reports completion; may not yet guarantee dependencies or actual endpoint responsiveness.
- **Port bound/listening:** the OS accepts sockets; business handlers may still return 503.
- **Readiness endpoint returns 200:** better if the endpoint checks the exact conditions required to receive traffic.
- **First business request succeeds:** measures the end-to-end path seen by real users, which may include lazy initialization, JIT warm-up, and connection establishment.
- **Steady-state throughput/latency:** measures an entirely different property from startup and must not be used in place of readiness.

**The choice of definition must serve the requirement:** for an HTTP service, "ready" is usually the health/readiness endpoint returning success according to criteria applied before the load balancer starts routing traffic. For a CLI tool, a reasonable milestone may be **producing the correct output and exiting**. For a batch worker, the ready milestone may be **having connected to the queue and being ready to accept jobs**, not the `main` method returning.

## 3. A Measurement Start Point Outside the JVM Is Required

To calculate **process-start-to-ready**, the measurement tool must capture a timestamp close to **process creation**. If you place:

```java
long started = System.nanoTime(); // start of main
initialize();
long elapsed = System.nanoTime() - started;
```

then you only measure **main-to-init**, omitting:

- OS process launch and the Java launcher.
- JVM runtime setup and native libraries needed before `main`.
- Class loading/initialization occurring before the marker.
- Certain startup hooks, agents, and premain logic.
- Timing differences for environment subprocess startup.

A marker inside `main` is still useful for **breaking down phases**, but should not be named **total process startup time**. To measure the total, an external harness outside the process is needed to invoke Java and receive the readiness signal.

### `System.nanoTime()` and `currentTimeMillis()`

- `System.nanoTime()` is designed to measure elapsed time via the difference between two calls **within an appropriate scope**; its absolute value must not be used as Unix epoch time.
- `System.currentTimeMillis()` reflects calendar wall clock time and can be adjusted by the system clock; it is not the best choice for measuring short durations.
- **Do not subtract two `nanoTime` values taken from two independent Java processes** assuming they share the same origin; each process/runtime/OS may have its own origin.
- The harness should use its own monotonic clock for T0→ready, such as Python's `time.monotonic_ns()` or the corresponding OS clock.

A **log timestamp** helps analyze the timeline, but a line with a delayed timestamp due to buffered logging does not necessarily reflect the exact moment the endpoint can serve requests.

## 4. The Readiness Contract Must Be Written Before Benchmarking

A readiness endpoint is only accurate when it reflects the ability to serve traffic according to the architecture:

- The server has started accepting requests.
- Required configurations, certificates, and resource pools are in place.
- Dependencies **required to serve the majority of requests** have been initialized/checked with appropriate timeouts.
- If there is a database, queue, or remote APIs, clearly define **when they are required for readiness** and the degraded mode policy.
- The worker has not been marked as shutting down.
- If the app uses lazy initialization, determine whether the ready definition accepts a **first-request penalty**; if not, the relevant paths must be warmed before ready.

**Liveness** and **readiness** are different:

- **`/live`:** the process is still capable of operating; a database outage does not necessarily fail liveness or force a restart loop.
- **`/ready`:** whether the system should send business requests to the instance **right now**.
- **`/startup`:** some orchestration platforms support a startup probe so the application has extra time to start before being restarted by liveness; the contract depends on the platform.

Using an endpoint that returns 200 as soon as the Java HTTP server accepts requests is a **transport signal**, not sufficient to represent a real application if the database/cache/schema is still not ready.

## 5. Java 17: A Server with a Readiness Endpoint for Measurement Practice

Create the file **`StartupReadyServer.java`**. The demo uses the `jdk.httpserver` module included in many **full JDK 17** distributions, requiring no external HTTP libraries:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

public class StartupReadyServer {
    private static volatile boolean ready;
    private static volatile long checksum;

    private static void reply(HttpExchange exchange, int code, String text)
            throws IOException {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(code, body.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
    }

    public static void main(String[] args) throws Exception {
        long mainStart = System.nanoTime();
        int port = args.length == 0 ? 18080 : Integer.parseInt(args[0]);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", port), 0);
        server.createContext("/live",
                e -> reply(e, 200, "alive\n"));
        server.createContext("/ready", e -> {
            if (ready) {
                reply(e, 200, "ready\n");
            } else {
                reply(e, 503, "not-ready\n");
            }
        });
        server.createContext("/work", e -> {
            if (!ready) {
                reply(e, 503, "not-ready\n");
            } else {
                reply(e, 200, "checksum=" + checksum + "\n");
            }
        });
        server.setExecutor(Executors.newFixedThreadPool(2));

        long result = 0;
        for (int i = 0; i < 10_000; i++) {
            result += i % 10;
        }
        checksum = result;

        server.start();
        ready = true;
        long elapsedMs = (System.nanoTime() - mainStart) / 1_000_000;
        System.out.println("READY port=" + port);
        System.out.println("mainToReadyMs=" + elapsedMs);
    }
}
```

Compile and start with **JDK 17**:

```bash
javac --release 17 --add-modules jdk.httpserver StartupReadyServer.java
java --add-modules jdk.httpserver StartupReadyServer 18080
```

In **another terminal** while the server is still running:

```bash
curl -i http://127.0.0.1:18080/live
curl -i http://127.0.0.1:18080/ready
curl -i http://127.0.0.1:18080/work
```

Once ready, the **body** parts are respectively:

```text
alive
ready
checksum=45000
```

The `mainToReadyMs=...` line contains a **dynamic measurement** with no fixed expected time. The `curl -i` command also prints status codes and headers, which also vary by HTTP server/runtime. The demo has no auto-shutdown mechanism: use **Ctrl+C** after finishing measurement. Port 18080 must be free; if busy, choose another port in both the Java command and the curl commands.

### Why Is Readiness in the Demo a Better Signal Than "main Has Run"?

- `/ready` returns **503** before the `ready` flag becomes true.
- `server.start()` has already been called before marking ready.
- Simple business data (`checksum`) is prepared before ready.
- The `/work` request returns a verifiable result, not just confirming that the socket is open.

This is still only a **small model**: a real service may need DB migrations, external dependencies, certificate loading, JIT warm-up, or queue subscription before readiness is valid. In the demo, `ready=true` may happen before the polling client actually connects; therefore, a good milestone for the harness to measure is the **first 200 response from the endpoint**.

## 6. Two Timing Measurement Points in the Demo Have Different Meanings

| Metric | Start | End | Includes |
| --- | --- | --- | --- |
| `mainToReadyMs` | Start of `main` | After `server.start()` and `ready=true` | Only initialization inside `main` from the marker |
| `processToReadyMs` | Before harness spawns subprocess | First HTTP `/ready` poll returning 200 | Launcher, JVM startup, app init, HTTP accept, poll overhead |
| `processToWorkMs` | Before subprocess | HTTP `/work` returns correct result | The first path of a business request |
| `readyToWarmMs` | Ready HTTP 200 | Defined warm throughput/latency condition reached | Lazy init, JIT, caches after ready |
| `coldStartToFirstByte` | Before subprocess or when request triggers start | Client receives first response byte | May include orchestration/router/network and request processing |

**Do not arbitrarily add durations together** if they already overlap. For example, `processToWorkMs` may include `processToReadyMs` if the harness checks readiness first, but not necessarily if the request takes a different path.

### Poll Interval Introduces Error into Ready Time

If the harness checks every 100 ms, the app may actually become ready between two probes. The time the first 200 is recorded will be **later** than the actual readiness time by an amount depending on polling/scheduling/network. To compare variants, use the **same probe interval**, endpoint, and timeout, and record the resolution/overhead of the measurement method.

## 7. External JVM Harness Example: Measuring Process-to-Readiness Multiple Times

The example below uses the **Python 3 standard library** to launch Java 17 separately for each trial and measure time with a monotonic clock. Python is an **external measurement tool outside the JVM**, not a Java SE source. Create the file **`measure_ready.py`** in the same directory containing `StartupReadyServer.class`:

```python
import statistics
import subprocess
import time
import urllib.error
import urllib.request

JAVA_CMD = [
    "java",
    "--add-modules", "jdk.httpserver",
    "StartupReadyServer",
    "18080",
]
URL = "http://127.0.0.1:18080/ready"
RUNS = 5
TIMEOUT_S = 30

def one_run():
    started = time.monotonic_ns()
    proc = subprocess.Popen(
        JAVA_CMD,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ready_ms = None
    try:
        deadline = time.monotonic() + TIMEOUT_S
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(
                    "JVM exited before readiness; inspect app logs"
                )
            try:
                with urllib.request.urlopen(URL, timeout=0.2) as response:
                    if response.status == 200 and response.read() == b"ready\n":
                        ready_ms = (time.monotonic_ns() - started) / 1e6
                        break
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
            time.sleep(0.02)
        if ready_ms is None:
            raise TimeoutError("Application did not become ready")
        return ready_ms
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

samples = [one_run() for _ in range(RUNS)]
print("runs=", RUNS)
print("medianReadyMs=", round(statistics.median(samples), 2))
print("minReadyMs=", round(min(samples), 2))
print("maxReadyMs=", round(max(samples), 2))
```

**Commands:**

```bash
javac --release 17 --add-modules jdk.httpserver StartupReadyServer.java
python3 measure_ready.py
```

The `medianReadyMs`/`minReadyMs`/`maxReadyMs` values are **measurements that must be taken on a real machine**, with no predicted timing stdout. `RUNS=5` is only suitable for **illustrative exercises**; reliable benchmark reports typically need more trials, interleaved variant ordering, and stopping/confidence criteria.

**Note the limitations of the sample harness:**

- Uses fixed port 18080: do not run in parallel with another server on the same port.
- Each trial kills the old process before launching the next trial; do not change ports while a server is still running.
- Poll interval ~20 ms plus connection/read cost creates resolution limits and error.
- Does not capture stderr/stdout to reduce logging impact, so if startup fails, run Java manually to see errors.
- Does not include network/orchestrator when actually deployed on Kubernetes/cloud separate from the client machine.
- OS file page cache/JIT shared archive may be **warm** after the first trial; results are not necessarily a **cold boot from disk**.
- The script spawns a separate process per trial but does not clear OS cache, DNS cache, shared filesystem cache, or change CPU frequency.
- If the old process still holds the port or was not cleanly killed, the trial may fail.
- `Popen` corresponds to the time the harness requests the process, not the exact nanosecond timestamp when the kernel first executes Java instructions.

Do not use this script to claim production-grade benchmark validity; it is a **measurable framework with the right readiness milestone**, which can be extended with logging and statistics.

## 8. Defining Cold Start and Warm Start by Environment

A Java application has multiple levels of "cold":

- **Fresh JVM process:** each run is a new Java process, but the OS page cache is still warm.
- **Cold class/JIT state:** new process, no runtime in-memory JIT profile/code cache yet; library data in disk cache may still be warm.
- **Cold application caches:** the application has not precomputed caches/pools/connections yet.
- **Cold OS file/page cache:** pages of JAR/JDK files are not yet in the filesystem cache; hard to reproduce and requires OS control.
- **Cold container image/node:** a new node must pull the image, mount layers, start the container, and set up namespaces/cgroups; not the same as a fresh Java process on a warm host.
- **Scale-to-zero request:** also includes load balancer/router, DNS/TLS/sidecar, scheduling, and image distribution, which can be much larger than JVM init.

Every report must state clearly the **start milestone** and what is already warm. Do not call a loop launching processes on the same laptop "cold container startup" if the image is already cached and JVM libs are already resident in the page cache.

### Testing Cold Startup Safely

Do not arbitrarily run commands to drop kernel page caches on a production/shared machine just to create a "cold" condition. It alters the entire host, affects other services, and does not reliably reflect the real environment. For cloud/containers, you can measure using a controlled new node/pod or resetting an isolated test environment; clearly note whether image pull/scheduler costs are within the metric scope.

## 9. Memory Footprint: Six Commonly Confused Numbers

| Metric | What It Measures | What It Does Not Mean |
| --- | --- | --- |
| **Heap used** | Bytes currently allocated on the JVM heap for objects/structures according to heap management and GC telemetry | RAM the process is using |
| **Heap committed** | Heap memory the JVM has committed for use; often differs from used | That all committed pages are physically resident |
| **Heap max** / `-Xmx` | Heap limit the JVM tries not to exceed according to configuration/ergonomics | RSS limit for the entire process |
| **Non-heap used/committed** | Metaspace, code cache, and pools classified by JMX as non-heap | All native memory |
| **RSS** | Resident Set Size: pages currently resident in physical memory attributed to the process by the OS | Java heap used size; also not unique private bytes |
| **PSS** (Linux) | Proportional Set Size: resident shared pages divided by the number of processes, useful when sharing memory | A portable Java SE API available on all OSes |

Other quantities include:

- **Virtual Size / VSZ:** virtual address space mapped/reserved; usually larger than RSS, not equal to actual RAM.
- **USS/private resident:** resident portion kept privately by the process, useful when multiple JVMs share libraries/CDS.
- **NMT reserved/committed:** HotSpot Native Memory Tracking's view of VM allocations/areas by subsystem; differs from RSS and has limited scope.
- **Container/cgroup `memory.current`:** total memory usage accounted by the cgroup, which may include process memory, page cache, and other parts; **must not be equated with the Java PID's RSS**.
- **Peak RSS / peak cgroup:** peak memory over an interval; a readiness snapshot may miss the peak.
- **Swap:** memory pages may be swapped out, making RSS low while latency worsens; must be observed additionally if the environment allows swap.

**Most importantly:** `-Xmx512m` does **not** mean the Java process only uses 512 MiB of RAM. HotSpot also needs native thread stacks, metaspace, code cache, GC metadata, direct buffers, JNI/native libraries, and other runtime regions.

## 10. Heap Used, Committed, Max: Standalone Java 17 Demo

Create the file **`HeapSnapshotDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

public class HeapSnapshotDemo {
    static volatile byte[] retained;

    static void printMemory(String label) {
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        System.out.println(label
                + " usedMiB=" + heap.getUsed() / (1024 * 1024)
                + " committedMiB=" + heap.getCommitted() / (1024 * 1024)
                + " maxMiB=" + heap.getMax() / (1024 * 1024));
    }

    public static void main(String[] args) {
        printMemory("before");

        retained = new byte[8 * 1024 * 1024];
        retained[0] = 1;
        retained[retained.length - 1] = 2;

        printMemory("after");
        System.out.println("arrayBytes=" + retained.length);
        System.out.println("endpoints="
                + (retained[0] + retained[retained.length - 1]));
    }
}
```

```bash
javac --release 17 HeapSnapshotDemo.java
java -Xms32m -Xmx128m HeapSnapshotDemo
```

**The last two stdout lines are deterministic:**

```text
arrayBytes=8388608
endpoints=3
```

The two `before/after` lines print **dynamic** numbers, varying by JDK build/GC/heap layout and runtime timing; do not fabricate expected used/committed values. With G1 region size/heap constraints, allocation may be managed differently than with other collectors. An array has an object header/padding, so **actual heap allocation may be larger than `arrayBytes`** (payload length).

Reading the measurements accurately:

- `getUsed()` is heap used at the time of the snapshot, **not cumulative allocated bytes**.
- `getCommitted()` is the capacity the JVM has committed for the heap, which can differ from `used`.
- `getMax()` may be `-1` for some memory pool/usage contexts where maximum is undefined; for total heap on common JVMs it relates to the heap limit.
- None of the three indicates the resident physical pages of the process.
- The `retained` variable intentionally holds a strong reference to the array so the demo has live data until the end of the program; an actual measurement needs to avoid code being eliminated by dead-code elimination.

### A Model Example of the Difference

Assume (hypothetical numbers):

```text
heap max        = 512 MiB
heap committed  = 256 MiB
heap used       = 120 MiB

native + mapped resident + other categories = 95 MiB
RSS OS          = 280 MiB

Reasonable conclusion:
  heap used ≠ committed ≠ heap max ≠ RSS.
```

The numbers are not measurements from `HeapSnapshotDemo`; they illustrate why you should **not** calculate RSS by adding a native estimate to heap used without checking actual mappings/pages.

## 11. Measuring Non-Heap and Metaspace via Java SE JMX

`ManagementFactory.getMemoryMXBean().getNonHeapMemoryUsage()` can return aggregate non-heap used/committed. To inspect each pool, read `MemoryPoolMXBean`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;

public class NonHeapPoolsDemo {
    public static void main(String[] args) {
        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            System.out.println(pool.getName()
                    + " -> " + pool.getUsage());
        }
    }
}
```

```bash
javac --release 17 NonHeapPoolsDemo.java
java NonHeapPoolsDemo
```

**No fixed stdout:** memory pool names, numbers, and non-heap partitioning depend on the collector, JVM implementation, and version; HotSpot 17 typically has pools for **Metaspace**, **Compressed Class Space** (when used), and **CodeHeap** segments.

**Do not read the Metaspace pool and assume you know all native memory.** Direct buffers, thread stacks, JVM internal arenas, and other native allocations are not necessarily included in JMX non-heap pools.

## 12. Measuring RSS on Linux and macOS/Windows

### Linux

While the Java PID is running:

```bash
ps -o pid,rss,vsz,comm -p <PID>
cat /proc/<PID>/status
cat /proc/<PID>/smaps_rollup
```

`<PID>` is a **placeholder**; replace it with the actual PID. Common fields:

- `VmRSS` in `/proc/<PID>/status`: RSS of the process according to the kernel.
- `VmHWM`: high-water mark RSS (resident peak reported by the kernel) over the process lifetime.
- `Rss` and `Pss` in `smaps_rollup`: resident and proportional resident for applicable mappings.
- `ps rss` on many Linux distributions reports **KiB** (check the man page); do not assume bytes.

`smaps_rollup` may require permissions/kernel support; deep reading in production has overhead. RSS may include file-backed mapped libraries/JDK archive pages shared with other processes, not just private Java pages.

### GNU time: Peak RSS at Process Exit

With GNU `/usr/bin/time`:

```bash
/usr/bin/time -v java -Xms64m -Xmx256m HeapSnapshotDemo
```

`Maximum resident set size (kbytes)` is the **peak RSS** according to the tool/OS during the process run, not the RSS right at readiness. If a server application does not exit, the server must be stopped in the test environment before reading the result; and the stop timing must be consistent across variants.

**Caution:** the shell builtin `time`, GNU `/usr/bin/time`, and other Unix systems have different outputs/options; `-v` is not a universal option across all systems.

### Windows PowerShell

You can observe the Java process:

```powershell
Get-Process -Name java |
    Select-Object Id, WorkingSet64, PeakWorkingSet64,
                  PrivateMemorySize64, VirtualMemorySize64
```

Values are usually in bytes. `WorkingSet64` is similar in concept to a resident working set but **does not equate perfectly to Linux RSS/PSS**. `PrivateMemorySize64` differs from Java heap used. Use `Get-Process -Id <PID>` if multiple Java processes exist. PowerShell labels/behaviors may vary by OS version.

### macOS

`ps -o rss` and `vmmap <PID>` can assist footprint investigation, but definitions/tools differ from Linux. Do not mix numbers from Windows WorkingSet, Linux RSS, and macOS footprint in a side-by-side comparison report without explanation.

## 13. Native Memory Tracking (NMT) for Analyzing HotSpot Memory

HotSpot has **Native Memory Tracking (NMT)** to estimate/record native memory categories managed by the VM. Enable **before starting the JVM**:

```bash
java -XX:NativeMemoryTracking=summary \
  --add-modules jdk.httpserver StartupReadyServer 18080
```

In another terminal with the appropriate Java PID:

```bash
jcmd <PID> VM.native_memory summary
jcmd <PID> GC.heap_info
jcmd <PID> VM.flags
```

`jcmd` requires JDK tools, the appropriate user/permissions, and a live process. NMT must be enabled from startup; do not assume all tracking levels can be enabled mid-lifecycle.

You can use baseline/diff when supported by the runtime:

```bash
jcmd <PID> VM.native_memory baseline
# Execute a well-defined workload
jcmd <PID> VM.native_memory summary.diff
```

**NMT reserved/committed is not RSS:**

- **Reserved:** virtual address space or memory ranges reserved; does not mean all are backed by physical pages.
- **Committed:** regions committed according to the allocator/VM; not necessarily immediately resident.
- NMT primarily tracks native allocations of **HotSpot/JVM**, **and does not cover all native allocations from third-party JNI libraries** or OS-side memory.
- NMT has memory/CPU overhead and can perturb startup timing; to measure "clean" startup performance, there must be runs without NMT.
- `NativeMemoryTracking=detail` provides more detail than `summary` but increases overhead and data volume; use only when needed.

### Why Can Comparing NMT with RSS Diverge?

RSS also counts resident pages of mapped files/shared libraries, heap pages, and native areas according to OS policy; NMT accounts in reserved/committed categories within the runtime and may not track every native subsystem. Do not require total "NMT committed" to equal "RSS" exactly; these are two different measurement models.

## 14. Container Memory: RSS Is Not the Entire Memory Budget

If Java runs inside a Linux container/cgroup v2, common metrics are:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.events
```

Paths only apply when the process is in a cgroup with the corresponding mount/path; in environments with nested cgroups or v1, the exact controller path must be determined. Some files (such as `memory.peak`) do not exist on older kernel/cgroup setups.

Meanings:

- `memory.current`: usage according to cgroup accounting at read time, which may include multiple processes and page cache according to the kernel.
- `memory.max`: hard limit when configured; the value `max` means there is no such cgroup limit according to the file.
- `memory.peak`: high-water mark usage of the corresponding cgroup.
- `memory.events`: events such as OOM/OOM kill per cgroup; counter semantics must be read carefully.
- The container metric does not necessarily equal the Java PID's RSS; sidecars/native helpers/shared page cache can contribute.

### Why Does a Container Get OOMKilled While Heap Used Is Still Low?

The Java heap is only part of the memory footprint. Native thread stacks, metaspace, direct buffers, JIT/code cache, JVM internals, JNI, mapped files, and page cache can push the cgroup to its limit. A process can also be killed by the cgroup **without having time to throw `java.lang.OutOfMemoryError`** in the Java heap.

When measuring startup gains in containers, report both **cgroup peak** and **process RSS** (when obtainable) rather than using only `MemoryMXBean.getHeapMemoryUsage().getUsed()`.

## 15. Peak, Snapshot, and Steady-State: Collect All Three

A service may:

1. Need a lot of memory to parse configuration/load data into objects.
2. Release many temporary objects after startup.
3. Have the JVM keep the heap committed.
4. Have RSS drop slowly or not drop alongside heap used due to page commitment/GC/OS policy.
5. When real traffic arrives, see thread stacks, caches, and direct buffers grow sharply.

Therefore, collect at least:

- **Peak during startup:** peak RSS/cgroup between process start and readiness.
- **At readiness:** RSS, heap used/committed, non-heap, NMT (if needed), process CPU time.
- **Steady state:** memory after a well-defined workload/warm-up (for example, after 5 minutes or N requests) along with throughput/p99.
- **After idle:** depending on serverless or scale-to-zero goals; memory footprint after idle time.
- **Peak under traffic:** if the application has bursts or lazy initialization.

A snapshot at T4 **can miss a peak that occurred at T2**. A high-water mark metric at process exit **does not tell whether the peak belonged to startup or serving** without a timeline.

## 16. Why Can Increasing `-Xms` Mislead Startup Memory?

`-Xms` adjusts the initial heap size, while `-Xmx` limits the maximum heap. Changing these flags can affect:

- Memory committed from the start and the heap's ability to expand.
- GC ergonomics and conditions for selecting heap configuration.
- Actual RSS if committed pages are touched during startup (do not equate committed with resident).
- Startup timing due to page commitment/initialization and GC overhead.
- Throughput/tail latency after ready.

Example experiment:

```bash
java -Xms64m -Xmx512m --add-modules jdk.httpserver StartupReadyServer 18080
```

Compare with another configuration after stopping the old process:

```bash
java -Xms256m -Xmx512m --add-modules jdk.httpserver StartupReadyServer 18080
```

**Do not draw conclusions before measuring**: `-Xms64m` may reduce committed heap at ready but alter heap growth/GC, without guaranteeing faster process-to-ready or a fixed percentage lower RSS. In particular, `-XX:+AlwaysPreTouch` can cause committed pages to be pre-touched, drastically changing startup cost and resident pages; if comparing, that flag must be controlled.

**Do not simultaneously change `-Xms`, `-Xmx`, collector, and concurrency** and attribute all changes to a single variable. Run disciplined A/B tests.

## 17. Class Data Sharing (CDS) and Memory Sharing

HotSpot's **Class Data Sharing (CDS)** can use an archive containing pre-processed metadata/class data to reduce some class loading overhead and allow sharing mapped pages across multiple Java processes. This can relate to both **startup time** and footprint, but must be observed on the actual JVM/runtime.

A way to **observe**, without forcing results:

```bash
java -Xshare:auto -Xlog:cds=info -version
```

In common HotSpot builds, `-Xshare:auto` lets the JVM use the archive if available; when the archive cannot be used, it can fall back according to the flag's semantics. `-Xshare:on` has a stricter policy and can make the JVM exit if the shared archive cannot be used. Do not assume that just passing `-Xshare:auto` guarantees the archive was used.

### CDS, AppCDS, and Shared Pages

- **Default CDS archive:** may be provided/generated by the JDK depending on distribution and installation method.
- **Application CDS (AppCDS):** requires a workflow to generate/use the archive matching the exact app/class path/module path/build; only use when an appropriate workload/class list is available.
- **Shared mapped pages:** two JVM processes using the same CDS/JDK libraries can share resident pages, causing the sum of each process's RSS to **double-count** shared pages.
- **PSS/USS** is more useful than standalone RSS when wanting to know the incremental memory cost of multiple replicas, though each metric has constraints.

**Do not conclude "CDS reduces RSS by X MiB" based on a single run.** On a single process, mapped shared archive pages may still make RSS look large, while the actual incremental memory for a second replica is lower. Compare **startup-to-ready** and **PSS/incremental cgroup footprint** according to the deployment model.

## 18. JIT and Tiered Compilation Trade-Off with Startup

For applications that run for a few hundred milliseconds and exit, class loading/JIT overhead can be significant. For servers running for hours, C2-optimized code can save substantial CPU after warm-up.

A HotSpot flag commonly used in **isolated experiments**:

```bash
java -XX:TieredStopAtLevel=1 \
  --add-modules jdk.httpserver StartupReadyServer 18080
```

This flag limits tiered compilation to C1 level 1 under common HotSpot policies; it **does not mean Java runs interpreter-only**. It can reduce some profiling/C2 compilation overhead and improve certain startup metrics on suitable workloads, but it can **reduce throughput or increase CPU-bound latency over the long run**.

Measurements to compare:

1. Process-to-readiness median/p95.
2. First business request duration.
3. Compilation CPU cost during startup (diagnostic run).
4. RSS/committed/code cache at ready.
5. 5–15 minutes of throughput/CPU/p99 after ready, if the app is long-lived.
6. Peak RAM when multiple replicas scale simultaneously.

Do not choose a startup optimization configuration based solely on a number-crunching method microbenchmark: **the actual ready bottleneck may lie in framework init/network/DB**, not JIT.

## 19. Does the GC Collector Affect Startup?

Different collectors can change:

- JVM/GC initialization work.
- Metadata, native memory, and background threads.
- Heap sizing/commit policies.
- Young/old GC pause behavior while the app starts.
- Memory footprint and throughput while serving traffic.

Example experiment changing **only one variable at a time**:

```bash
java -XX:+UseSerialGC -Xms64m -Xmx512m \
  --add-modules jdk.httpserver StartupReadyServer 18080
```

Compare against the default collector **on the same JDK 17/container/heap**. `SerialGC` may suit small, CPU-constrained processes or short-lived workloads, but is not "always fastest at startup"; GC pauses and throughput under load must be measured.

**Note:** do not pass `UseSerialGC` and `UseG1GC` together as if two collectors can be used simultaneously. JVM flags/ergonomics of each JDK and container may select a different collector. Record `-XX:+PrintFlagsFinal` and `-Xlog:gc*=info` in a **diagnostic run** if you need to know the actual collector in use.

## 20. Reducing Dependencies and Lazy Initialization: Beware of Shifting Costs

Techniques to reduce work required before ready:

- Remove unused dependencies/framework modules.
- Avoid overly broad classpath scanning when more precise configuration is available.
- Remove eager initialization of caches not needed for the first request.
- Initialize client/database pools on demand and configure connection timeouts.
- Use lazy initialization for rarely used features.
- Reduce the number of synchronous external calls required at startup.
- Use CDS/AppCDS in appropriate environments.
- Reduce non-essential logging/diagnostics work before ready.

However, it is very easy to **shift the cost to the first request**:

```text
Before:
  startup-to-ready = 800 ms
  first-request    = 30 ms

After lazy initialization (model):
  startup-to-ready = 500 ms
  first-request    = 380 ms

If traffic arrives right after ready, the experience may be worse.
```

These are **hypothetical numbers for explanation**, not benchmark results. A good readiness contract must specify which dependencies/cache paths need to be warmed before announcing 200.

### Lazy Init and Fault Tolerance

If deferred initialization can fail on the first request, the service has already marked itself ready even though it cannot serve part of the workload. This may be acceptable for optional features with graceful degradation, but unacceptable if that dependency is mandatory for all requests. **Defining "ready" is an operational decision**, not just an optimization trick.

## 21. CLI and Batch Applications: Readiness May Be Completion

For a Java CLI utility, meaningful milestones may be:

- From OS spawn to stdout having the **correct result**.
- From OS spawn to **exit code 0** after completing the job.
- From queue task dispatch to worker picking up the job; or time to finish processing the job.
- From container create to batch completion (including image pull if that is the goal).

Example of what not to do:

```bash
time java -version
```

This command measures the launcher/JVM version-print path, **not representing the startup of a business application with many dependencies**. It can be used as an informative low baseline, but do not substitute it for real service performance.

For CLI tools, falsely fast results because the JVM did not execute the required logic are completely misleading. Ensure **correct output, production-like code paths**, and equivalent input data before reading timing.

## 22. Comparing Baseline and Candidate Must Keep All Other Factors Identical

A/B design table:

| Dimension | Baseline A | Candidate B |
| --- | --- | --- |
| Source/application release | Same commit/build logic | Same commit if comparing JVM flags only |
| JDK vendor/version/build | Specific Java 17.0.x | Same as A |
| CPU/cores, RAM, disk | Same machine/VM/container | Same as A |
| Cgroup memory/cpu limits | Fixed | Fixed |
| `-Xms/-Xmx` | Explicitly recorded | Change only if it is the test variable |
| CDS/GC/tiering | Record all flags | Change intentionally only |
| Startup dependencies | Controlled DB/queue/network state | Equivalent to A |
| Readiness definition | Same endpoint and response validation | Same as A |
| Probe interval/timeout | Same | Same as A |
| Run count/order | N trials, interleaved A/B | N trials, interleaved |
| Workload after ready | Same input, concurrency, duration | Same as A |
| Output correctness | Required pass | Required pass |

If the goal is to compare **two JDKs**, of course the JDK build is the intentional variable; keep the remaining factors equivalent. If comparing **CDS**, archives/JARs/classpaths must be prepared properly on both variants.

### Why Interleave A/B?

If you run 20 times A and then 20 times B, toward the end of the test the OS page cache and CPU temperature may change, making B appear better/worse due to ordering. Interleaving or randomizing A/B helps reduce **systematic drift**, though it does not automatically create strict independence of samples. Record order timestamps, host load, and environmental factors.

## 23. Reading Statistics: Median, p95, Variance, CI

Startup time often has a non-normal distribution: occasional spikes due to JIT/GC, CPU scheduling, host noise, or remote dependencies. A "mean-only" table can hide variance.

- **Median (p50):** typical startup of the sample set.
- **p90/p95/p99:** tail startup; requires enough samples for percentiles to be meaningful.
- **Min/max:** observed bounds; min often benefits from page cache/lucky scheduling.
- **Std deviation / IQR:** dispersion; interpret alongside distribution shape.
- **Bootstrap CI or appropriate method:** expresses uncertainty of the estimate.
- **Outliers:** do not automatically discard them just because they "make numbers look bad"; investigate the cause or report with a pre-defined filtering method.

**Do not take `p99` from 5 trials as a reliable conclusion.** With a small sample, extreme percentiles mostly reflect a few observations and have very high uncertainty. Choose the number of trials based on noise, budget, and confidence requirements, rather than using a fixed number for every workload.

### Warm-Up for Server Benchmarks Differs from Startup Tests

In **each startup trial**, the process must be fresh if you want to measure init/JIT from a cold process. However, to evaluate **steady state**, you need to let the server run and warm the workload before measuring throughput.

**Do not warm up the JVM first, then measure time from there and call it cold process startup.** At the same time, do not measure throughput immediately after process ready and report that steady state has been reached if lazy-init/JIT code is still warming up.

## 24. Formulas for Evaluating Gains and Trade-Offs

With A as baseline and B as candidate:

```text
timeSavedMs = readyMsA - readyMsB

timeImprovementPct = (readyMsA - readyMsB) / readyMsA * 100

rssChangeMiB = rssB - rssA

rssChangePct = (rssB - rssA) / rssA * 100
```

For metrics where lower is better (startup, RSS, p99 latency), a **positive sign on `timeImprovementPct`** means B improves time; a positive sign on `rssChangePct` means B **uses more RSS**.

A **purely hypothetical** example:

| Metric | Baseline A | Candidate B | Interpretation |
| --- | ---: | ---: | --- |
| Median process-to-ready | 900 ms | 660 ms | Reduced 240 ms (~26.7%) |
| p95 process-to-ready | 1,200 ms | 970 ms | Reduced 230 ms |
| RSS at ready | 120 MiB | 135 MiB | Increased 15 MiB (12.5%) |
| Peak cgroup startup | 175 MiB | 185 MiB | Increased 10 MiB |
| First request p95 | 45 ms | 70 ms | Worse by 25 ms |
| Throughput steady state | 5,000 req/s | 4,400 req/s | Decreased 12% |

**Example conclusion:** B starts up faster but increases RAM and reduces throughput. If the target is serverless scale-to-zero with a sufficiently generous RAM limit, the trade-off may be acceptable **when the first-request penalty is carefully considered**. If the service runs continuously and needs high throughput, B may be disadvantageous.

**There is no universal "startup score".** Pre-define operational thresholds/SLOs: "ready p95 under N seconds, RSS peak under M MiB, steady-state throughput drop no more than K%, correctness pass". SLOs depend on the product; do not invent generic N/M/K values for all systems.

## 25. Java 17: Percentage Calculation Program Independent of JVM Timing

Create the file **`StartupBenefitMath.java`**:

```java
public class StartupBenefitMath {
    static double improvementPct(double oldValue, double newValue) {
        if (oldValue <= 0) {
            throw new IllegalArgumentException("baseline must be positive");
        }
        return (oldValue - newValue) * 100.0 / oldValue;
    }

    public static void main(String[] args) {
        double beforeMs = 900.0;
        double afterMs = 660.0;
        double beforeRss = 120.0;
        double afterRss = 135.0;

        System.out.printf(java.util.Locale.ROOT,
                "timeSavedMs=%.0f%n", beforeMs - afterMs);
        System.out.printf(java.util.Locale.ROOT,
                "timeImprovement=%.1f%%%n",
                improvementPct(beforeMs, afterMs));
        System.out.printf(java.util.Locale.ROOT,
                "rssChangeMiB=%.0f%n", afterRss - beforeRss);
        System.out.printf(java.util.Locale.ROOT,
                "rssChange=%.1f%%%n",
                (afterRss - beforeRss) / beforeRss * 100);
    }
}
```

```bash
javac --release 17 StartupBenefitMath.java
java StartupBenefitMath
```

**Deterministic stdout:**

```text
timeSavedMs=240
timeImprovement=26.7%
rssChangeMiB=15
rssChange=12.5%
```

The numbers 900/660/120/135 are all **hypothetical numbers to teach the calculation**. The program **does not measure** startup or RSS itself; to evaluate an app, take numbers from the harness and OS/container tools and compute with the same formulas.

## 26. Measuring Memory Without Distorting Startup Timing

A common mistake is enabling all diagnostics during the baseline but disabling them when measuring the candidate. NMT, JFR, class-loading logs, and thread dumps can all impact startup/memory.

The design should have **two experimental tracks**:

1. **Clean performance runs:** minimal instrumentation, same external probe metrics, same JVM flags except the test variable; collect time-to-ready and external RSS/cgroup sampling.
2. **Diagnostic runs:** enable NMT/JFR/GC logs/class-load logs to explain why; accept the overhead, but do not mix numbers directly into clean A/B comparisons.

Example enabling JFR **from JVM startup**:

```bash
java -XX:StartFlightRecording=filename=startup.jfr,dumponexit=true,settings=profile \
  --add-modules jdk.httpserver StartupReadyServer 18080
```

Recording with `dumponexit=true` writes when the JVM exits appropriately; you must stop the demo with Ctrl+C/signal and verify that `startup.jfr` was actually created. JFR has overhead and event configuration depends on the JDK build; do not promise a specific event will always be present.

**JFR helps inspect class loads, compilation, GC, threads/events, and CPU samples depending on event availability**, but cannot replace an external readiness marker or OS RSS. When accurate memory at ready is needed, take a direct snapshot or an external sampler.

## 27. Warm-Up Still Matters After the Application Is Ready

A server may open its port and return 200 when the compiler has only run C1, without JIT-optimizing hot routes yet. If traffic is sent right then:

- First requests incur additional lazy class loading and dependency resolution.
- JIT profiling, C2 compilation, or deoptimization can spike CPU.
- TLS/JDBC caches are not warm yet.
- The garbage collector does not have enough activity yet to stabilize GC ergonomics.
- Tail latency is higher than after warm-up.

Two design approaches:

**A. Ready early:** accept a warm-up period while serving; suitable if first-request latency SLOs allow it, if load balancer prewarming exists, or if traffic is low.

**B. Ready after warming a set of representative paths:** startup-to-ready is longer, but first-request latency is more stable. Do not run an artificial loop just to trigger JIT that differs from production code paths; it can skew profiles and fail to be representative.

Report both metrics together: **time to ready** and **time to first acceptable latency/throughput**, avoiding optimizing only a single milestone.

## 28. Measuring Multiple Replicas: Summing RSS Directly Can Double-Count

If 10 JVM processes map the same CDS archive or shared libraries, summing `RSS(PID1)+...+RSS(PID10)` can **double-count the same physical pages**. To estimate total node/cgroup memory:

- Observe **cgroup `memory.current`/`peak`** for the group of processes (understanding shared accounting).
- Observe **PSS** per process on Linux when permissions and kernel support exist.
- Compare **incremental node/cgroup memory** when scaling replicas 1→2→N in a controlled environment.
- Distinguish app heap/private anonymous resident from file-backed/shared pages.
- Note memory cache, sidecars, GC threads, and OS memory accounting.

**Hypothetical example:** RSS of each JVM is 150 MiB, of which 30 MiB is shared pages of the same JDK/lib archive; two JVMs do not automatically consume 300 MiB of physical private RAM. However, you also cannot simply compute 2×(150−30)+30 if there are other shared mappings, page cache, and different OS accounting; measure directly.

## 29. A Recommended Benchmark Sheet/CSV Schema

For each trial, record these fields:

```text
experiment_id
variant
trial_index
jdk_vendor
jdk_version
jdk_build
jvm_flags
os_kernel
cpu_model
cpu_quota
memory_limit
container_image_digest
app_commit
process_start_monotonic_ns
readiness_http_status
ready_elapsed_ms
first_work_success_ms
rss_ready_kib
rss_startup_peak_kib
cgroup_memory_ready_bytes
cgroup_memory_peak_bytes
heap_used_ready_bytes
heap_committed_ready_bytes
native_memory_tracking_enabled
steady_state_rps
steady_state_p95_ms
steady_state_p99_ms
failure_reason
```

This is a **recommended column format**, not an actual results CSV. Only fields that can be collected consistently should be used for comparison; fill in missing when no number is available, **do not substitute 0**, because 0 implies it was measured and actually used zero memory/time.

If startup fails (nonzero exit, readiness timeout, dependency unavailable), record a **failure trial** and the reason. Do not arbitrarily drop failed trials and report "fast and stable startup".

## 30. Bias from the Operating System and Deployment Environment

Sources of noise that are not Java bugs:

- **OS page cache:** JAR/JDK classes may already be resident after a few trials.
- **Filesystem/network storage:** container image layers or network file mounts cause differing read times.
- **CPU quota/throttling:** a CPU-limited container may take more wall-clock time even when CPU work is unchanged.
- **Host contention:** other processes competing for CPU/cache/memory bandwidth.
- **CPU frequency/thermal:** turbo boost, power saving, and temperature cause drift.
- **NUMA placement:** page faults/thread placement differ on multi-socket machines.
- **DNS/TLS/database health:** external latency and timeouts can dominate ready time.
- **Logging/tracing/agents:** Java agents, JFR, NMT, and class-load logging add overhead.
- **Image pull/scheduling:** depending on the metric, can account for most of total scale-to-zero latency.
- **Clock granularity/probe cadence:** overly coarse polling hides small improvements.
- **GC timing and heap ergonomics:** initial heap/committed differences cause variance.
- **Security/antivirus scanning:** can affect file loads on desktop/Windows.
- **Stale processes/port collision:** polling an old process's endpoint by mistake makes ready time artificially near 0.

### Special Note: Verify Process Identity When Polling

A harness using a fixed port can hit a bug: the old process has not exited yet and the endpoint still returns 200, causing the new trial to be recorded as "ready" before the new JVM has actually started. The sample above **terminates the process on each trial**, but in a stronger benchmark you should:

- Use a fresh port for each trial or a process-specific token.
- Verify the PID/process serving the endpoint and port ownership.
- Wait for the old process to exit completely and verify the port is released.
- Record a failure if the new subprocess exits early.
- Never report success when connecting to the wrong server.

This is a real-world bug that can produce a very convincing yet meaningless "0–20 ms startup".

## 31. Wrong Conclusions About Memory

| Wrong Conclusion | Truth |
| --- | --- |
| "`-Xmx` equals the JVM's RAM limit" | `-Xmx` only limits the **Java heap**, excluding native footprint |
| "Low heap used means low RSS too" | Heap committed, metaspace, code cache, stacks, and native allocations still consume memory |
| "Heap committed is all resident RAM" | Committed differs from resident physical pages |
| "VSZ 4 GiB means the JVM consumes 4 GiB RAM" | Virtual reserved address space does not equal RSS |
| "Sum of RSS across 10 replicas = unique physical RAM" | Shared mappings/CDS may be double-counted |
| "NMT total committed must equal RSS" | NMT and OS RSS have different coverage/accounting |
| "NMT tracks every JNI allocation" | NMT does not cover all third-party native memory |
| "Metaspace equals all native memory" | It is only one region/component |
| "Container `memory.current` equals one Java PID's RSS" | cgroup may include multiple processes/cache |
| "Readiness RSS sufficiently represents peak" | Startup may have a temporary peak before ready |
| "When GC runs, RSS must drop immediately" | JVM/OS commit, page reclamation, and GC policy decide |
| "Lowering `-Xms` always reduces startup time" | It is only a trade-off that must be measured; GC/heap growth may change |
| "Changing GC only affects pauses, not footprint" | GC implementations have their own threads, metadata, and sizing policies |

## 32. Wrong Conclusions About Startup

| Wrong Conclusion | Truth |
| --- | --- |
| "Once the Java process is created, the app is ready" | The JVM and application still have initialization work |
| "Start of `main` is the total startup milestone" | Omits launcher and JVM initialization before `main` |
| "Port listening means able to serve business requests" | Endpoint may return 503 or dependencies may not be ready |
| "Log 'Started' is an absolute milestone" | Log buffering/ordering does not replace an external readiness probe |
| "First-request latency must equal ready time" | First request has different lazy init, TLS, and code warm-up |
| "One faster trial proves an optimization" | OS caches, scheduler, and polling introduce noise |
| "JMH method benchmark measures process startup" | JMH measures hot/steady-state microbenchmarks per its harness |
| "Enabling `PrintCompilation` does not change timing" | Diagnostics have overhead |
| "CDS always reduces process RSS" | Shared mappings have different accounting and must be measured |
| "`TieredStopAtLevel=1` is always better than default" | Can reduce steady-state throughput |
| "`SerialGC` is always the best startup collector" | Depends on workload, heap, CPU, and SLA |
| "Lazy init always improves user experience" | Can shift cost to the first request and increase failures |
| "Container start to ready is the same as Java launch-to-ready" | Container setup/image pull/sidecars are separate parts |
| "p99 of five trials is trustworthy" | Sample size is too small to infer tail confidence |
| "Warm run on host = cold startup" | OS page cache may still be warm |
| "A flag changed together with JDK/app build can still be analyzed" | Confounding variables; design must be controlled |

## 33. A Reproducible Evaluation Process

**Step 1 — Define success criteria.** Specify what the endpoint/operation returns, which status codes, and which dependencies must be ready. Distinguish liveness/ready/first request.

**Step 2 — Define milestone T0.** Java process created, container started, pod scheduled, or request arriving at serverless platform? Do not mix milestone types.

**Step 3 — Lock down the environment.** Record JDK vendor/version, OS/CPU, cgroup limits, JAR/image digest, framework flags, and dependencies state.

**Step 4 — Choose baseline A.** Save current JVM flags, initial/max heap, GC, CDS, and tiered policy.

**Step 5 — Choose exactly one change B.** For example, only enable CDS, only change `TieredStopAtLevel`, only reduce eager initialization, or only change `-Xms`.

**Step 6 — Build an external harness.** Spawn the JVM/process, poll readiness with timeout, verify HTTP 200 + body/process identity, stop cleanly, and log errors.

**Step 7 — Run multiple independent trials.** Record failed runs as well, interleave A/B order, and do not treat a single run as a benchmark.

**Step 8 — Collect memory at the same milestones.** RSS at ready, peak RSS during startup, heap used/committed (if needed), and cgroup `memory.current`/`peak`. Do not compare KiB vs MiB inconsistently.

**Step 9 — Collect first-request metric.** Ensure candidate B did not merely defer initialization to the first request.

**Step 10 — Collect steady-state.** For long-lived servers, measure throughput/CPU/p95/p99 after a representative warm-up.

**Step 11 — Run diagnostics separately.** Use JFR/NMT/GC/class load logs to explain root causes without skewing the clean comparison.

**Step 12 — Compute deltas and uncertainty.** Median/p95/time saved, RSS change/peak, failure rate, and confidence; do not just report "faster".

**Step 13 — Verify correctness.** Real requests/CLI output/batch results must be equivalent; readiness must not report 200 too early.

**Step 14 — Decide based on SLO.** Is faster startup worth higher RAM/lower throughput? Does it fit scale-to-zero, batch, or long-lived services?

**Step 15 — Check for regressions.** Run in a production-like environment with real images/builds and similar constraints; keep A/B logs for reproducibility.

## 34. Self-Check Questions

**Question 1:** Why is `mainToReadyMs` not total startup?

Because it starts **after** Java launcher/JVM initialization before `main` is called.

**Question 2:** Once a server has bound a port, is it definitely ready?

**No.** Dependencies/handlers may not be able to respond yet; a business-meaningful readiness condition is required.

**Question 3:** Does `-Xmx512m` limit process RSS to 512 MiB?

**No.** Heap is only part of the footprint.

**Question 4:** Is there any contradiction if Heap used = 100 MiB, committed = 300 MiB, RSS = 350 MiB?

**No.** The three metrics measure different aspects.

**Question 5:** Why is peak RSS needed in addition to RSS at ready?

Startup may allocate temporary memory and release it before ready, causing a snapshot to miss the peak.

**Question 6:** Must NMT committed and OS RSS match byte for byte?

**No.** They have different coverage and accounting.

**Question 7:** Why can `-XX:TieredStopAtLevel=1` make startup faster but worsen steady-state throughput?

It changes JIT/tiering and prevents deep C2 optimization under normal policy; the trade-off depends on the workload.

**Question 8:** Does CDS always reduce RSS on a single process?

**Not guaranteed.** Shared archive pages may still be counted in RSS; PSS/incremental footprint has a different meaning.

**Question 9:** Why not use five trials to claim p99 startup?

Tail percentiles require enough observations; five trials have too much uncertainty.

**Question 10:** Why does `memory.current` not equal `ps rss` of Java?

Cgroup can account for multiple processes/page cache and other memory types compared to per-PID RSS.

**Question 11:** Does lazy initialization making readiness faster guarantee it is better?

**No.** It can make the first request slow or fail, increase peak, and cause latency spikes.

**Question 12:** Can a harness polling every 100 ms accurately measure a 5 ms improvement?

**Unlikely.** Poll quantization/scheduling can mask the improvement; an appropriate probe design is needed.

**Question 13:** Why must clean and diagnostic runs be executed separately?

NMT/JFR/logging have overhead that can alter the very startup timing/memory being measured.

**Question 14:** When measuring a Java CLI tool, is a readiness endpoint mandatory?

**No.** Appropriate milestones can be **correct business output or successful process exit**.

**Question 15:** If B reduces ready by 20% but RSS +30% and first-request p95 worsens, should B be chosen?

**Cannot be decided from % ready alone.** Must consider SLOs, RAM budget, traffic patterns, throughput, and workload reality.

## 35. Java 17 References and Related Tools

- [Oracle Java SE 17 — `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xms`, `-Xmx`, `-Xshare`, `-XX` flags, GC logging, JFR startup.
- [Oracle Java SE 17 — `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `GC.heap_info`, `VM.native_memory`, `VM.flags`, `JFR.start`/`dump`.
- [Oracle Java SE 17 — Java HotSpot Virtual Machine Performance Enhancements](https://docs.oracle.com/en/java/javase/17/vm/java-hotspot-virtual-machine-performance-enhancements.html): CDS, tiered compilation, and HotSpot optimizations.
- [Oracle Java SE 17 — Class Data Sharing](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html): CDS goals and shared archive mechanics in this version.
- [Oracle Java SE 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): `reserved`/`committed`, coverage, and overhead.
- [Oracle Java SE 17 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/index.html): GC/heap ergonomics, collector trade-offs.
- [Java SE 17 — `Runtime.totalMemory`/`freeMemory`/`maxMemory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): heap capacity-related API.
- [Java SE 17 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html) and [`MemoryUsage`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): used/committed/max in heap and non-heap.
- [Java SE 17 — `MemoryPoolMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): pools such as Metaspace/CodeHeap (JVM-dependent).
- [Java SE 17 — `System.nanoTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): measuring duration, not interpreting absolute values.
- [Java SE 17 — `jdk.httpserver` module](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): demo server and HTTP contexts.
- [OpenJDK JFR — Flight Recorder](https://openjdk.org/jeps/328): runtime profiling tool and startup recording.
- [Linux kernel cgroup v2 memory documentation](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#memory): `memory.current`, `memory.max`, `memory.peak`, and counters.
- [Linux proc `proc_pid_status`](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html) and [`proc_pid_smaps`](https://man7.org/linux/man-pages/man5/proc_pid_smaps.5.html): VmRSS/VmHWM/PSS and memory mapping accounting.
- [GNU time](https://www.gnu.org/software/time/): `/usr/bin/time -v` and peak RSS on supported systems.

**Conclusion:** A startup improvement is only trustworthy when you **accurately measure time from process/container start to meaningful readiness**, check **first-request/steady-state trade-offs**, and report **RSS or cgroup peak** in addition to heap used/committed. Java 17 provides sufficient tools for this: a ready endpoint, an external monotonic harness outside the JVM, `MemoryMXBean`, `jcmd` NMT/JFR, and OS/container metrics. Run multiple trials under equivalent conditions, maintain a baseline, present uncertainty, distinguish real measurements from hypothetical examples, and conclude based solely on **SLOs and total application cost**.

# Evaluating Startup Time and Actual Memory Usage Under Spring Boot Lazy Initialization

## 1. Objective: Verify Lazy Initialization by Measurement, Not Gut Feel

In Spring Boot, **lazy initialization** allows deferring the creation of certain beans until a bean is actually requested. For normal singleton beans, the default initialization mode is eager: the container creates many beans during `ApplicationContext` refresh. When lazy initialization is enabled, part of that work can shift to first use. That often helps **shorten certain startup milestones**, yet does not automatically make the whole application faster or reduce memory usage once all features have been exercised.

A sound evaluation must separately answer at least four questions:

1. **Startup time:** how much do the durations from process start to `ApplicationReadyEvent` and to the readiness probe genuinely returning healthy change?
2. **First-use latency:** how much extra delay does the first request/job initializing deferred beans incur, and does it breach SLOs?
3. **Actual memory:** how do RSS/container memory and JVM heap used change at ready, after first use, and during steady state?
4. **Operational risk:** are configuration errors previously caught at startup pushed to the first request; are probes, traffic, and warm-up appropriate?

**Do not draw effectiveness conclusions solely from the `"Started ... in ... seconds"` log line or the `-Xmx` flag size.** Ready time, cold requests, warm requests, and memory footprint at different points in time are distinct quantities.

### Three Hypotheses to Test

- H1: `spring.main.lazy-initialization=true` can reduce startup time to the ready milestone for the same artifact and configuration.
- H2: certain initial API calls experience higher latency because beans/metadata must be created when requests arrive.
- H3: memory at ready may be lower, yet after all business paths are warmed up, the difference may shrink or disappear; laziness does not guarantee lower peak memory.

Outcomes are **application-specific**, depending on the dependency graph, auto-configuration, web framework, initialized resources, GC, JVM, CPU, traffic, and which beans are actually invoked. All benchmark numbers must be gathered on real machines rather than guessed.

## 2. Eager vs. Lazy Mechanics: Where Does the Work Move?

An `ApplicationContext` typically initializes non-lazy singletons during refresh. For lazy beans, the container stores the bean definition and only creates the bean when there is real demand. Global lazy can be enabled via:

~~~properties
spring.main.lazy-initialization=true
~~~

Or YAML:

~~~yaml
spring:
  main:
    lazy-initialization: true
~~~

By default, this setting is `false`. It can also be configured in Java:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setLazyInitialization(true);
app.run(args);
~~~

The Java snippet is a **code fragment**, requiring an appropriate `MyApplication` class. Do not mix all three configuration styles unless you know exactly which property source determines the final effective value.

### Initialization Graph

~~~mermaid
flowchart TD
  A["SpringApplication.run"] --> B["Create ApplicationContext"]
  B --> C["Register and process BeanDefinitions"]
  C --> D{"Is bean eager or required by a dependency?"}
  D -->|"Yes"| E["Create bean during startup"]
  D -->|"No"| F["Keep bean definition, do not create instance yet"]
  E --> G["ApplicationReadyEvent"]
  F --> G
  G --> H["First request / job"]
  H --> I{"Need deferred bean?"}
  I -->|"Yes"| J["Create bean on first use, inject, init callbacks, proxy"]
  I -->|"No"| K["Use already-ready beans"]
  J --> L["Execute business logic"]
  K --> L
~~~

**Laziness does not guarantee every bean remains uninitialized.** A lazy bean required by an eager singleton via direct constructor injection can still be created at startup to satisfy the dependency. Factories, infrastructure beans, web mappings, `BeanFactoryPostProcessor`s, and other required components may also need early preparation.

### Why Is Startup Faster Yet the First Request Slower?

If creating a bean takes 300 ms:
- **Eager:** 300 ms is counted in startup before ready; subsequent requests can use it right away.
- **Lazy:** 300 ms may be absent from startup; the first request touching the bean pays that cost.

This is an **explanatory model**, not a measured metric of your application. A bean can also trigger dependency chains, class loading, connection pool opening, or proxy generation; hence the cost does not necessarily reside only in one class's constructor.

### Laziness Delays Error Detection

Spring Boot documents an important warning: if a bean is misconfigured yet uncreated, startup can still succeed; exceptions only surface on first use. Therefore an application that becomes "ready" faster is not necessarily safer to deploy if first-hit failures or rollback risks rise.

For beans that must be checked during startup, use `@Lazy(false)` on the appropriate bean definitions to preserve early initialization even when global lazy is on, or design an intentional warm-up/validation gate before readiness. Every such choice changes benchmark results and must be documented.

## 3. Accurately Distinguishing the Timestamps to Measure

| Metric | Start → End Milestone | Meaning | Pitfalls |
| --- | --- | --- | --- |
| `T_process_ready` | Process start → readiness probe returns healthy | Time until the deployment system truly sees the instance ready | Affected by polling interval, HTTP/probe initialization |
| `T_main_ready` | Beginning of `main` → `ApplicationReadyEvent` callback | Bootstrap time inside the JVM after entering `main` | Excludes JVM launch before `main`; precedes the readiness event right after ready |
| `T_first_hit` | Sending first business request → receiving response | Cold-start latency of a path using deferred beans | Includes network/HTTP, serialization, and deferred initialization |
| `T_warm_hit` | Warm request → response | Latency once dependencies exist and JIT/caches may be warm | Needs enough requests and identical inputs |
| `T_workload_ready` | Process start → predefined business warm-up finishes | Time until **all required paths** are ready to serve | Cannot be inferred from `ApplicationReadyEvent` alone |
| `T_startup_variation` | Across multiple independent processes | Median/p95 distribution of startup | A single run is usually unrepresentative |
| `T_gc_pause` | GC pause durations under the same workload | Evaluates GC cost from heap/allocations | Must not be confused with total startup time |

### Spring Boot `StartedEvent` Differs from `ReadyEvent`

In a typical successful startup:

~~~mermaid
flowchart LR
  A["JVM/process launch"] --> B["main()"]
  B --> C["ApplicationContext.refresh()"]
  C --> D["ApplicationStartedEvent"]
  D --> E["LivenessState.CORRECT"]
  E --> F["ApplicationRunner / CommandLineRunner"]
  F --> G["ApplicationReadyEvent"]
  G --> H["ReadinessState.ACCEPTING_TRAFFIC"]
  H --> I["Readiness probe / router observes"]
~~~

`ApplicationStartedEvent` fires after refresh yet before runners. `ApplicationReadyEvent` fires after runners. Boot publishes `ReadinessState.ACCEPTING_TRAFFIC` after `ReadyEvent`. Thus measuring `ApplicationStartedEvent` and calling it "ready to accept traffic" can be wrong; even measuring inside an `ApplicationReadyEvent` listener is still **slightly earlier** than an external system observing a healthy readiness probe.

**Recommendation:** record at least both `T_main_ready` and `T_process_ready`. Both are useful when defined consistently, yet neither replaces the other.

## 4. Actual Memory: Do Not Confuse Heap, RSS, and Container Limits

| Parameter | What It Reflects | Is It Actual Resident Memory? |
| --- | --- | --- |
| `-Xmx` / max heap | Ceiling on heap the JVM is allowed to use | No: it is a limit, not bytes currently used |
| `-Xms` / initial heap | Configured initial heap size | Does not automatically mean all pages are resident |
| Heap **used** | Java objects currently accounted as live/used in heap | Only one part of the JVM footprint |
| Heap **committed** | Memory the JVM has committed to the heap | Different from heap used and RSS |
| Non-heap JVM | Metaspace, class metadata, code cache, and certain other JVM regions | Not everything lives on the heap |
| Direct/native memory | Direct buffers, thread stacks, native libraries, JVM internals | Can increase RSS even when heap used stays flat |
| Process RSS | Total resident physical memory pages attributed to the process, including shared pages depending on OS | Suitable for assessing process footprint; private vs. shared cannot be trivially split |
| Container memory | Memory accounted by cgroup/OS for the container | May include page cache and other components depending on runtime/cgroup |

**A lazily created bean can keep heap and RSS lower at ready yet cause a jump on the first request.** Therefore capture multiple checkpoints:

- M0: after JVM/process launch yet before context ready, if tooling allows;
- M1: **ready, before touching any business endpoint**;
- M2: immediately after the **first request** using deferred beans;
- M3: after warming key business paths and letting GC/traffic stabilize;
- M4: peak over a representative load window, e.g., 10–30 minutes or longer if the workload requires it.

No universal formula guarantees `RSS_lazy < RSS_eager` at every checkpoint. Laziness can even cause bunched allocations, GC pressure, or simultaneous peaks when initial traffic hits many beans concurrently.

### About Reserved vs. Committed

The JVM can **reserve** large virtual address ranges for heap/class space; that number is not physical RAM in use. With Native Memory Tracking, distinguish `reserved` from `committed`, and do not mechanically sum every NMT category and treat it as RSS.

### Measuring from Inside the JVM

Heap used can be observed via MXBean:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

MemoryUsage usage = ManagementFactory.getMemoryMXBean()
        .getHeapMemoryUsage();

long heapUsedBytes = usage.getUsed();
long heapCommittedBytes = usage.getCommitted();
long heapMaxBytes = usage.getMax();
~~~

This is a snippet placed inside a Java method, not a standalone file. Heap used fluctuates with GC; a point-in-time reading does not prove whether a bean was freed or leaked.

## 5. Designing a Fair A/B Experiment

To compare lazy vs. eager, the two runs **must differ in only one intentional variable**: `spring.main.lazy-initialization=false` vs. `true`. Keep identical:

1. **Artifact:** the exact same JAR and dependencies, without rebuilding between modes.
2. **JDK/JVM:** same vendor, Java version, `-Xms`/`-Xmx` flags, GC, CPU architecture.
3. **Environment:** same machine/container limits, CPU count, background load, port/network path.
4. **Configuration:** same active profiles, external config, logging, database URL, feature flags, secret sources.
5. **Workload:** same URL/HTTP method sequence, payload size, concurrent clients, warm-up counts, and observation duration.
6. **Cache/JIT:** run multiple independent processes, alternating or randomizing A/B order; document cold vs. warm filesystem cache.
7. **Probe:** same readiness path/interval; do not treat "listening port" as readiness if startup tasks remain.
8. **Observation:** same method for measuring RSS, heap used, latency, percentiles, and errors; avoid attaching a profiler to only one group.
9. **Validity:** both modes must return correct business results; a mode that is faster because it skipped broken initialization **is not a win**.
10. **Replication:** run multiple independent trials per mode (e.g., 10–20 runs), reporting median, spread, and p95 when sample count suffices.

### Note on CPU and Container Environments

Under low CPU quotas, bean creation and JIT can experience throttling. The same JAR on a multi-core laptop versus a 1-CPU pod can behave very differently. Record `cpu.max`/CPU quota, memory limit, JVM version, GC, and co-located processes on the node. Do not compare staging measurements against a production pod running a different workload and attribute differences to laziness.

### Run Ordering

Do not run all eager trials first and all lazy trials afterward: filesystem cache, background load, and CPU thermals can skew results. A simple pattern is alternating **E–L–L–E** across rounds, with each trial in a fresh process, waiting for the prior process to exit completely before starting the next.

Comparing inside the same process by toggling the property after `ApplicationContext.refresh()` **is invalid**: lazy initialization is decided while building the context and bean definitions; changing a property at runtime does not "uncreate" existing beans.

## 6. Spring Boot 3.5.x, Java 17+ Example to Measure Both Startup and First-Hit

The illustrative project uses Spring Boot 3.5.16, Java 17+, Maven, Spring Web, and Actuator. It includes a memory-heavy `HeavyCatalog` bean with an **artificial 250 ms delay** strictly to make the effect easy to observe in a learning setting. **Do not use this number as a production benchmark:** when measuring real apps, replace the dummy bean with real beans and remove `Thread.sleep`.

Structure:

~~~text
lazy-benchmark/
├── pom.xml
└── src/main/
    ├── java/com/example/benchmark/
    │   ├── LazyBenchmarkApplication.java
    │   ├── HeavyCatalog.java
    │   └── WorkController.java
    └── resources/
        └── application.yaml
~~~

### 6.1 File `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>lazy-benchmark</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2 File `src/main/resources/application.yaml`

~~~yaml
spring:
  application:
    name: lazy-benchmark
  main:
    banner-mode: "off"
    # lazy-initialization not fixed: CLI decides per run.

server:
  port: 8081

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

`management.endpoint.health.probes.enabled=true` enables the readiness endpoint in this Actuator web experiment. Port `8081` can be overridden with `--server.port=...`. Do not expose all Actuator endpoints publicly merely to measure ready.

### 6.3 File `src/main/java/com/example/benchmark/LazyBenchmarkApplication.java`

~~~java
package com.example.benchmark;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;

@SpringBootApplication
public class LazyBenchmarkApplication {

    public static void main(String[] args) {
        long mainStartNanos = System.nanoTime();

        SpringApplication app =
                new SpringApplication(LazyBenchmarkApplication.class);

        // Listener registered before run; works even when global lazy=true.
        app.addListeners((ApplicationListener<ApplicationReadyEvent>) event -> {
            long elapsed = System.nanoTime() - mainStartNanos;
            System.out.println("MAIN_TO_READY_MS="
                    + TimeUnit.NANOSECONDS.toMillis(elapsed));
        });

        app.run(args);
    }
}
~~~

**Why use `System.nanoTime()`?** It is suitable for measuring **duration within the same JVM**, not wall-clock timestamps. `MAIN_TO_READY_MS` excludes the JVM launcher overhead before `main` starts and does not measure when kubelet observes the probe. To measure from outside the process to readiness, use the script in Section 7.

### 6.4 File `src/main/java/com/example/benchmark/HeavyCatalog.java`

~~~java
package com.example.benchmark;

import java.util.Arrays;

import org.springframework.stereotype.Component;

@Component
public class HeavyCatalog {
    private final byte[] payload = new byte[24 * 1024 * 1024];

    public HeavyCatalog() {
        Arrays.fill(payload, (byte) 7);

        // Only to illustrate initialization cost; DO NOT use sleep
        // in production benchmarks.
        try {
            Thread.sleep(250);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Catalog initialization interrupted", e);
        }

        System.out.println("HEAVY_BEAN_CREATED");
    }

    public String status() {
        return payload[0] == 7 ? "warm" : "invalid";
    }
}
~~~

This bean holds an array of roughly **24 MiB** on the heap and performs a fill so memory pages are touched. `Thread.sleep(250)` illustrates how initialization cost **can** shift from startup to the first request. Sleep is not real CPU workload; therefore do not interpret this benchmark as matching a real database/cache bean.

### 6.5 File `src/main/java/com/example/benchmark/WorkController.java`

~~~java
package com.example.benchmark;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {
    private final ObjectProvider<HeavyCatalog> catalogProvider;

    public WorkController(ObjectProvider<HeavyCatalog> catalogProvider) {
        this.catalogProvider = catalogProvider;
    }

    @GetMapping("/status")
    public String status() {
        return "OK";
    }

    @GetMapping("/work")
    public String work() {
        return catalogProvider.getObject().status();
    }
}
~~~

**Design detail critical to experiment validity:** the controller injects `ObjectProvider<HeavyCatalog>`, not `HeavyCatalog` directly via constructor. The provider **does not force target creation when the controller is constructed**. That gives lazy mode the opportunity to defer `HeavyCatalog` creation until `/work` calls `getObject()`.

With default eager mode, the non-lazy `HeavyCatalog` bean is still pre-instantiated during context refresh even though the controller holds a provider. When global `lazy=true`, this bean is not pulled early by a direct eager dependency, so typically the first `/work` call creates it.

If you replace the provider with:

~~~java
public WorkController(HeavyCatalog catalog) {
    // ...
}
~~~

while the controller stays eager, the dependency can pull `HeavyCatalog` into startup. Therefore **always check the `HEAVY_BEAN_CREATED` log** to confirm which phase actually created the bean instead of blindly trusting a config flag.

### 6.6 Build and Run Both Modes

~~~bash
mvn -q -DskipTests package

# Mode A: eager, Spring Boot default
java -Xms64m -Xmx256m \
  -jar target/lazy-benchmark-0.0.1-SNAPSHOT.jar \
  --spring.main.lazy-initialization=false \
  --server.port=8081
~~~

In another terminal, once the application is ready:

~~~bash
curl -i http://127.0.0.1:8081/actuator/health/readiness
curl -fsS http://127.0.0.1:8081/status
curl -fsS http://127.0.0.1:8081/work
~~~

When both endpoints work properly, the two business-route response body lines are:

~~~text
OK
warm
~~~

`MAIN_TO_READY_MS=...` varies by machine, and `HEAVY_BEAN_CREATED` appears during the startup phase in eager mode. No fixed millisecond number is guaranteed.

Stop the process completely and run mode B:

~~~bash
java -Xms64m -Xmx256m \
  -jar target/lazy-benchmark-0.0.1-SNAPSHOT.jar \
  --spring.main.lazy-initialization=true \
  --server.port=8081
~~~

In mode B, before calling `/work`, call only readiness and `/status`; inspect the logs to see whether `HEAVY_BEAN_CREATED` has appeared yet. In the normal demo configuration, it has not appeared yet. Calling `/work` for the first time logs it; subsequent calls reuse the singleton.

**Note:** line-continuation backslashes `\` are for Bash/Unix. In Windows PowerShell/cmd, run `java -jar ...` on one line or use the shell's own line-continuation syntax.

### 6.7 Expected Results by Phase Without Fabricating Numbers

| Observation | Eager `false` | Lazy `true` |
| --- | --- | --- |
| Heavy bean created during refresh | Usually yes | Usually not yet |
| `HEAVY_BEAN_CREATED` before ready | Yes in demo | No in demo |
| `MAIN_TO_READY_MS` | Includes heavy bean creation | May exclude it |
| First `/work` request | Uses already-created bean | May pay 24 MiB bean creation + 250 ms sleep |
| Subsequent `/work` requests | Does not recreate singleton | Does not recreate singleton |
| RSS at ready | Potentially higher | Potentially lower |
| RSS after calling `/work` | Has 24 MiB array | Also has 24 MiB array |
| Peak/latency under concurrent load | Must measure | Must measure; cold init cost may bunch |

The words "potentially"/"may" in the table are deliberate. Do not promise an exact 24 MiB RSS gap or an exact 250 ms startup speedup: JVM heap allocation, GC, page residency, lazy web initialization, scheduling, and probes all make real measurements differ from a simplified model.

## 7. Linux A/B Measurement Script Using Bash, `curl`, and `ps`

Below is a **runnable** script for Linux environments with Java 17+, Maven, `curl`, GNU `date`, `ps`, and Bash. It starts a fresh process, waits for actual readiness, captures RSS at ready, calls `/work` first and second times, and captures RSS afterward.

**File `measure-one.sh`**:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: bash measure-one.sh true|false PORT" >&2
  exit 2
fi

mode="$1"
port="$2"

if [[ "$mode" != "true" && "$mode" != "false" ]]; then
  echo "First argument must be true or false" >&2
  exit 2
fi

jar="target/lazy-benchmark-0.0.1-SNAPSHOT.jar"
log="run-$mode-$port.log"

# Linux/GNU date: nanoseconds since epoch.
start_ns=$(date +%s%N)

java -Xms64m -Xmx256m \
  -jar "$jar" \
  "--spring.main.lazy-initialization=$mode" \
  "--server.port=$port" \
  >"$log" 2>&1 &
pid=$!

cleanup() {
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}
trap cleanup EXIT

ready=0

# 400 iterations * 0.05s: ~20s check limit
# excluding each curl request's duration.
for ((i=0; i<400; i++)); do
  if curl -fsS -o /dev/null \
       "http://127.0.0.1:$port/actuator/health/readiness" \
       2>/dev/null; then
    ready=1
    break
  fi

  if ! kill -0 "$pid" 2>/dev/null; then
    echo "Process exited before readiness. Inspect $log" >&2
    exit 1
  fi

  sleep 0.05
done

if [[ "$ready" -ne 1 ]]; then
  echo "Readiness timeout. Inspect $log" >&2
  exit 1
fi

ready_ns=$(date +%s%N)
external_ready_ms=$(( (ready_ns - start_ns) / 1000000 ))

rss_ready_kib=$(ps -o rss= -p "$pid" | tr -d ' ')

first_hit_s=$(curl -fsS -o /dev/null \
  -w '%{time_total}' "http://127.0.0.1:$port/work")

second_hit_s=$(curl -fsS -o /dev/null \
  -w '%{time_total}' "http://127.0.0.1:$port/work")

rss_after_work_kib=$(ps -o rss= -p "$pid" | tr -d ' ')

printf 'mode=%s ready_ms=%s rss_ready_kib=%s first_s=%s second_s=%s rss_after_kib=%s\n' \
  "$mode" "$external_ready_ms" "$rss_ready_kib" \
  "$first_hit_s" "$second_hit_s" "$rss_after_work_kib"

# These two lines are observation signals, not fixed numbers.
grep -E 'MAIN_TO_READY_MS=|HEAVY_BEAN_CREATED' "$log" || true
~~~

**Notes about the script:**

- One run = one fresh process, avoiding comparing eager and lazy in the same JVM.
- The script captures `start_ns` **before launching the Java process**, so it differs from `MAIN_TO_READY_MS` inside the JVM.
- It checks readiness via a successful HTTP status; if the endpoint returns an error or refuses connection, the loop keeps polling. Note each poll has its own overhead and the health endpoint itself may trigger lazy web beans.
- `ps -o rss=` reports RSS in **KiB** on typical Linux systems; do not treat it as MB without converting units.
- `curl -w '%{time_total}'` returns seconds (with fractional decimals), including connection setup / HTTP client and server overhead; localhost reduces but does not eliminate noise.
- The script writes logs in the working directory and terminates the process on exit, keeping logs for inspection.
- Measuring **right after** the first request is not steady-state; to measure M3/M4, add warm-up time, request load, and periodic sampling.

After building the JAR, run trials in interleaved order:

~~~bash
bash measure-one.sh false 18081
bash measure-one.sh true 18081
bash measure-one.sh true 18081
bash measure-one.sh false 18081
~~~

Repeat across more rounds on a quiet machine. Because the script stops each trial's process on exit, port `18081` can be reused once released. If the port has not cleared, the script will time out and you should check for leftover processes; never launch two runs on the same port simultaneously.

For real metrics, copy the `mode=...` lines into a CSV/table and analyze median, min/max, and distribution. **Never base decisions on the first run alone.**

### Sample Recording Table

| Run | Mode | Main→Ready (ms) | External→Readiness (ms) | RSS ready (MiB) | First `/work` (ms) | Warm p95 (ms) | RSS post-warm (MiB) | GC/Errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | eager | measure | measure | measure | measure | measure | measure | record |
| 2 | lazy | measure | measure | measure | measure | measure | measure | record |
| 3 | lazy | measure | measure | measure | measure | measure | measure | record |
| 4 | eager | measure | measure | measure | measure | measure | measure | record |

**Formulas:**

~~~text
startup_reduction_pct =
    100 * (median_ready_eager - median_ready_lazy)
        / median_ready_eager

rss_ready_delta_mib =
    median_rss_lazy_ready_mib - median_rss_eager_ready_mib

cold_penalty_ms =
    median_first_hit_lazy_ms - median_first_hit_eager_ms
~~~

All denominators must be non-zero, using consistent timing definitions and environments. A negative `startup_reduction_pct` means lazy mode was slower in that dataset, not a formula error.

To measure meaningful warm p95/p99 latency, you need **many requests** and a proper load-testing tool such as k6, wrk, Gatling, or JMeter; two requests in the sample script are not enough for reliable percentiles.

## 8. Observing the JVM with `jcmd`, GC, and Native Memory Tracking

### `jcmd GC.heap_info`

On a machine with a compatible JDK and permission to attach to the Java process:

~~~bash
jcmd "$pid" GC.heap_info
~~~

`$pid` is the running JVM PID, e.g., from the script or `jps -l`. The command prints heap/GC metrics appropriate for the JVM and collector. Interpretation varies across G1, Parallel, ZGC, and different JVMs; do not write parsers tied to one output format without pinning collector and version.

### Native Memory Tracking

To inspect memory regions **outside the heap**, enable NMT at **process startup**:

~~~bash
java -XX:NativeMemoryTracking=summary \
  -Xms64m -Xmx256m \
  -jar target/lazy-benchmark-0.0.1-SNAPSHOT.jar \
  --spring.main.lazy-initialization=true
~~~

Then run in another terminal:

~~~bash
jcmd PID VM.native_memory summary
jcmd PID VM.native_memory baseline
# After a warm-up phase:
jcmd PID VM.native_memory summary.diff
~~~

Replace `PID` with the actual process ID. Depending on OS/JVM and user permissions, attach may be disabled. NMT tracks HotSpot internal allocations such as Java Heap, Class, Thread, Code, GC, and other native categories. **NMT does not cover all native allocations outside the JVM**, and NMT itself adds overhead; Oracle notes measurable performance impact when tracking is enabled. Therefore **do not enable NMT on only one A/B arm and compare startup times**: if NMT is needed, enable the identical setting on both arms or separate it into a diagnostic run.

**Proper interpretation:** NMT `reserved` is not RSS; `committed` does not automatically equal heap used. Read NMT alongside RSS and Java heap metrics to see whether deferred costs sit in Java allocations, class loading, threads, or native regions.

### GC and Allocations

With Java 17 HotSpot, enable unified logging to observe GC:

~~~bash
java -Xms64m -Xmx256m -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -jar target/lazy-benchmark-0.0.1-SNAPSHOT.jar \
  --spring.main.lazy-initialization=true
~~~

When comparing, keep logging configuration identical across both modes. Distinguish **GC count, pause time, allocation rate, and live heap set**. An application creating fewer objects at startup can allocate them in a burst at first traffic; peak pauses and latency can be worse despite a faster ready time.

### Java Flight Recorder and `ApplicationStartup`

Spring Framework provides `ApplicationStartup` and `StartupStep` to profile bean/context initialization. With Spring Boot 3.5.x, configure:

~~~java
SpringApplication app =
        new SpringApplication(LazyBenchmarkApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(2048));
app.run(args);
~~~

This is an **alternative** to the `SpringApplication` construction in `main` from Section 6, requiring the `org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup` import. To keep `MAIN_TO_READY_MS`, call `setApplicationStartup(...)` on the existing `app` before `run` instead of creating two separate `SpringApplication` instances.

With Actuator, `/actuator/startup` can expose startup steps from `BufferingApplicationStartup` when configured and exposed. Example configuration **only in a secured benchmark environment**:

~~~properties
management.endpoints.web.exposure.include=health,startup
~~~

Never accidentally expose startup/actuator details on the public Internet; enforce proper authentication, authorization, and network policies. The startup snapshot from the endpoint captures steps during context initialization; **it does not measure first-hit of deferred beans if those steps happen after startup outside the recording window**. To analyze both deferred initialization and JVM allocations, use JDK Flight Recorder and/or a profiler through the post-first-request window.

A complementary option is swapping in `FlightRecorderApplicationStartup` and running JFR:

~~~bash
java -XX:StartFlightRecording=filename=lazy-startup.jfr,duration=30s \
  -jar target/lazy-benchmark-0.0.1-SNAPSHOT.jar \
  --spring.main.lazy-initialization=true
~~~

You must configure `FlightRecorderApplicationStartup` on `SpringApplication` for JFR to record Spring's corresponding startup steps; `StartFlightRecording` alone only enables JFR for configured JVM events. Do not use a profiler for baseline timing if the profiler imposes asymmetric overhead between the two modes.

## 9. Evaluating First-Hit Latency and Concurrent Load

A common evaluation mistake is concluding "lazy is better because startup is 20% faster" without measuring the first request or immediate post-deploy traffic bursts.

### First-Hit Is Not Warm Latency

Distinguish:
- **Cold process:** newly started JVM; beans/context/class loading may be incomplete.
- **First functional request:** initial request to a given business path, potentially pulling an uncreated dependency chain.
- **Warm requests:** requests after beans, connection pools, JIT, and caches have been initialized representatively.
- **Concurrent cold burst:** many initial requests needing one lazy singleton or several beans concurrently; can cause contention and high tail latency.

`HeavyCatalog` in the demo is a singleton so only one instance is created, yet concurrent requests can still block waiting on first-time bean creation. Never substitute a single sequential client's `T_first_hit` for p99 during a multi-client burst.

### Assessing Which Features Need Pre-Traffic Warm-Up

List your **critical-path** business routes, for example:
- health/readiness endpoints;
- login/session validation;
- primary database read/write operations;
- endpoints serving the majority of traffic;
- message consumers and schedulers;
- authentication, serialization, or remote clients with heavy initialization.

Run controlled warm-up before opening routes, while understanding that **warm-up shifts part of the cost back before readiness**. That can be the right choice when stable p95/p99 matters more than the shortest possible ready time.

### Do Not Use Warm-Up Requests That Mutate Real Data

Calling an endpoint to warm it up might write to the DB, emit events, or trigger jobs, causing side effects. Use idempotent/safe endpoints, staging environments, or a restricted internal warm-up API. Never hit production endpoints with side effects solely for performance testing.

## 10. Biases That Render Results Meaningless

### Measuring Only One Trial

JIT, filesystem cache, GC, CPU scheduling, and class loading vary across runs. A single run does not show the distribution. Run multiple interleaved processes and record logs and host conditions.

### Comparing Lazy RSS at Ready Against Eager RSS After Serving Traffic

Those are two different load states. Compare M1 with M1, and M3 with M3. If lazy merely has not created the beans yet, lower early RSS is a **deferred cost**, not eliminated memory.

### Confusing Low `-Xmx` with Low RAM Usage

`-Xmx` is the Java heap ceiling. Setting `-Xmx256m` does not mean the process uses only 256 MiB RSS; beyond heap lie metaspace, thread stacks, code cache, direct buffers, and OS/runtime overhead.

### Computing Latency from Misaligned Log Milestones

A `Started ... in ...` log measures Spring's internal boundary and excludes external readiness probe waiting. Use an internal monotonic clock and a separate external stopwatch, always recording exact start/end boundaries.

### Forgetting That Laziness Can Push Broken Beans into Runtime

In eager mode, a misconfigured essential bean can fail startup. In lazy mode, the first endpoint touching it fails with an exception. Before deploying, put mandatory startup checks on an appropriate eager/warm-up path or use `@Lazy(false)` for beans that must not fail late.

### Measuring Memory Using Total NMT Reserved

Reserved virtual address space is not resident RAM. Use RSS/container memory, heap used, and committed memory to understand each layer rather than mixing units.

### Ignoring Warm-Up and GC

Right after the first endpoint call, heap used can spike temporarily due to short-lived objects not yet collected. Capture identical milestones across multiple GC cycles without manually forcing full GCs just to get "prettier" numbers (which alters measurement conditions).

### Changing Multiple Settings Simultaneously

If you enable lazy while also changing `-Xmx`, GC, logging, and thread pools, you cannot tell which change caused the outcome. Split experiments into two phases: (1) isolate the lazy effect, (2) tune JVM or application policies separately afterward.

### Treating Startup Readiness as a Proxy for Throughput

Reaching ready quickly does not mean higher throughput. Measure request rate, error rate, p50/p95/p99, CPU, GC, peak RSS, and upstream dependency behavior under representative load.

## 11. Rollout Architecture: Global, Selective, or Disabled?

| Approach | Potential Benefits | Drawbacks | When to Consider |
| --- | --- | --- | --- |
| Default eager | Catches config/DI errors early; steadier first-hit | Slower startup and higher ready RSS | Systems with strict correctness/latency requirements |
| Global lazy `true` | Can lower ready time and early RSS | Shifts errors and init costs to runtime | Services with many rarely used beans and tolerable cold hits |
| Selective `@Lazy` | Defers only rare beans; bounded risk | Requires knowing dependency graph; eager deps can pull bean | A few heavy beans off the hot path |
| Global lazy + `@Lazy(false)` on critical beans | Preserves early validation/critical paths | Less startup savings than pure global lazy | Clear separation of essential vs. optional beans |
| Lazy + pre-readiness warm-up | Avoids cold hits on main routes | Warm-up returns cost to startup; must avoid side effects | Strict first-request SLAs |
| Optimize real bean init (I/O, scans, classpath, pools) | Improves both startup and runtime | Requires profiling/engineering effort | When JFR/`ApplicationStartup` pinpoints clear bottlenecks |

**The final choice must be driven by deployment goals**, not a setting claimed to be optimal in every case.

### When Rollback Is Needed

If lazy increases cold-hit p99 or runtime errors, you need a clean way to roll back the property to `false`, restart according to policy, and verify readiness of the new instances. Because this is a startup option, changing the property inside an already-refreshed context does not reconstruct the bean graph under the new mode.

## 12. What Should a Benchmark Report Look Like?

A decision-grade report needs:

**Environment details:** commit/artifact hash, Spring Boot version, JDK vendor/version, JVM flags, active profiles, CPU quota, memory limit, machine type, OS, replica count, workload spec.

**Startup metrics:** median/p95 of `T_main_ready` and `T_process_ready` across multiple independent runs. Document event capture, polling interval, and measurement resolution.

**Latency metrics:** first-hit on critical endpoints; warm latency p50/p95/p99 under representative concurrency, error rates, and timeouts.

**Memory:** RSS at ready, post-warm-up, and peak; JVM heap used/committed, direct/native where available; memory limits and OOM events.

**Reliability:** startup exceptions, errors appearing only on first request, probe failures, and rollout behavior.

**Conclusion:** are the gains/costs large and consistent enough to meet SLOs; are `@Lazy(false)`, warm-up, or selective lazy needed?

Summary template (do not fill numbers until measured):

~~~text
Artifact: <commit / digest>
JDK / Boot / GC / CPU quota: <recorded configuration>
Comparison: eager(false) vs lazy(true), same JAR and workload
Independent runs per variant: <N>
Median main-to-ready: eager <ms>; lazy <ms>
Median external readiness: eager <ms>; lazy <ms>
First-hit p95 /work: eager <ms>; lazy <ms>
Warm p95 /work: eager <ms>; lazy <ms>
RSS ready: eager <MiB>; lazy <MiB>
RSS after warm-up: eager <MiB>; lazy <MiB>
Peak container memory: eager <MiB>; lazy <MiB>
Startup errors / first-hit errors: <counts>
Decision: <enable / selective / keep eager>
Reason: <SLOs, risks, representative evidence>
~~~

The angle brackets here are **report template placeholders**, not real metrics. When reporting on a real system, fill them with verifiable measured data.

## 13. Self-Check Questions

**1. Does setting `lazy=true` guarantee all beans are created after ready?**  
No. Infrastructure beans, beans required by eager dependencies, and startup-supporting beans can still be created early.

**2. Why can ready be faster while the first request is slower?**  
Because beans, proxies, class loading, and resources are initialized on first use instead of during startup.

**3. If lazy RSS at ready is 30 MiB lower, can you conclude 30 MiB is saved for the lifetime of the app?**  
No. You must measure after the workload uses deferred beans and at peak; RSS is also more than heap alone.

**4. Is `-Xmx` a measure of resident RAM?**  
No. It is the maximum Java heap limit, not RSS.

**5. Why shouldn't you rely solely on `ApplicationStartedEvent` timing?**  
Because it fires before runners and accepting readiness; the app may not yet be ready to receive traffic.

**6. To measure from process launch until the readiness probe succeeds, where should the clock sit?**  
Outside the JVM, starting before the `java` command and stopping when the probe succeeds, noting polling/HTTP overhead.

**7. In the example, why does the controller use `ObjectProvider<HeavyCatalog>`?**  
So the controller does not force target resolution when constructed; `getObject()` in `/work` is where the deferred bean can be requested.

**8. What happens if `@Lazy(false)` is used under global lazy?**  
The marked bean can be kept eager for early initialization/validation; still inspect the real dependency graph.

**9. Should you enable NMT only on the lazy arm and compare startup against eager?**  
No. NMT adds overhead and breaks A/B equivalence.

**10. Why measure heap used, RSS, and container memory separately?**  
They measure different layers; the JVM has non-heap/native costs and containers have their own accounting.

**11. When laziness hides a misconfigured bean until the first request, how should you handle it?**  
Keep validation/essential beans eager or perform controlled warm-up before accepting traffic; do not treat startup success as proof of functional correctness.

**12. To decide whether to enable lazy in production, what metrics are needed beyond median startup?**  
First-hit p95/p99, warm latency, errors, post-warm RSS/heap, peak memory, GC, and readiness/rollout behavior.

## 14. Official Documentation for Cross-Reference

- [Spring Boot 3.5 — SpringApplication: Lazy Initialization](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): properties, enable/disable APIs, and warnings about startup/memory/late errors.
- [Spring Framework — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html): on-demand bean creation, lazy singletons, and relationship with eager dependencies.
- [Spring Boot 3.5 — Application Startup Tracking](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): `ApplicationStartup`, `BufferingApplicationStartup`, and JFR.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): health/readiness endpoints and the startup endpoint.
- [Spring Boot — Actuator Startup REST API](https://docs.spring.io/spring-boot/api/rest/actuator/startup.html): snapshot/drain startup steps.
- [Oracle JDK 17 — jcmd Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `GC.heap_info`, `VM.native_memory`, and JVM diagnostics.
- [Oracle JDK 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): NMT scope, reserved/committed, and overhead.
- [Oracle JDK 17 — java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xms`, `-Xmx`, and JVM diagnostic flags.

**Technical conclusion:** evaluating lazy initialization is not a contest over a single startup number. Enable lazy initialization only when **properly phase-matched** ready-time and memory reductions outweigh cold-hit costs and late-error risks, while continuing to satisfy latency, availability, and memory SLOs under representative load.
# Monitoring Process, CPU, Uptime, and Open Files

## 1. Identifying Exactly What Is Being Observed

When an application slows down or stops accepting new connections, a heap snapshot alone is not enough to explain why. You need to know how the JVM process is using CPU, how long it has been running, how many processors are available in the environment, and whether the process still has headroom for file descriptors.

Three boundaries must be distinguished:

- **JVM process:** includes application threads and internal JVM threads; not just a single request or controller.
- **Operating environment seen by the JVM:** may be a physical host, a virtual machine, or a container environment; do not assume every "system" value covers the entire physical node.
- **A specific instance:** process metrics generally belong to one JVM. They do not automatically become aggregate figures for an entire application cluster.

In Spring Boot Actuator, built-in metrics binders connect JVM/operating-system management information to Micrometer. This lesson references **Spring Boot 3.3.0, Micrometer 1.13.0, and Java 17+**; data availability also depends on the JDK, operating system, permissions, and actual runtime configuration.

## 2. Map of Metrics to Read

| Micrometer Name | Typical Statistic in the Illustrated Version | Unit/Semantics | Scope |
| --- | --- | --- | --- |
| `process.cpu.usage` | `VALUE` | Recent CPU utilization ratio, typically 0..1 when valid | JVM process |
| `system.cpu.usage` | `VALUE` | Recent CPU ratio of the operating environment | Environment provided by the MXBean |
| `system.cpu.count` | `VALUE` | Number of processors available to the JVM | JVM perspective |
| `process.cpu.time` | `COUNT` | Cumulative CPU time; binder 1.13.0 sets unit `ns` | JVM process |
| `system.load.average.1m` | `VALUE` | One-minute load average; not a percentage | OS/JVM dependent |
| `process.uptime` | `VALUE` | Elapsed time since JVM startup | JVM process |
| `process.start.time` | `VALUE` | JVM startup timestamp from Unix epoch | JVM process |
| `process.files.open` | `VALUE` | Number of open file descriptors | Process, when platform-supported |
| `process.files.max` | `VALUE` | File descriptor limit reported by the MXBean | Process, when platform-supported |

In the `SimpleMeterRegistry` used in the lab, the two uptime/start-time metrics are output in seconds. Registries/exporters have their own unit conventions; always read `baseUnit` instead of guessing from the name or number magnitude.

In particular, `process.files.max` contains the word `max` in the **metric name**, but its measurement statistic is `VALUE`: the current limit value read from the source. It is not a `MAX` statistic recording the highest number of open files ever observed.

## 3. Built-In Infrastructure and Querying via Actuator

In Boot 3.3, `SystemMetricsAutoConfiguration` provides `UptimeMetrics`, `ProcessorMetrics`, and `FileDescriptorMetrics` binders when the metrics infrastructure conditions are met. The presence of a binder does not guarantee that every OS-specific measurement will be registered.

Ordinary Boot applications do not need to re-declare these binders just to read built-in metrics. The standalone Java program at the end of this lesson calls `bindTo()` manually because it does not run Boot auto-configuration infrastructure. [SystemMetricsAutoConfiguration 3.3.0](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/SystemMetricsAutoConfiguration.java).

### 3.1. Preparing a Boot Web Application

In a Boot web project that already has `spring-boot-starter-web` and `spring-boot-starter-actuator`, expose the metrics endpoint over HTTP, for example using a local configuration:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    metrics:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,metrics
```

If the application has security configuration, endpoint access still follows that configuration. Substitute the right port/base path if the project customized them; do not expose all of Actuator just to obtain these metrics.

### 3.2. Discovering Names Before Reading Values

```bash
curl -i http://127.0.0.1:8080/actuator/metrics
```

Look up the actual `process.*` and `system.*` names, then inspect details:

```bash
curl -s http://127.0.0.1:8080/actuator/metrics/process.uptime
curl -s http://127.0.0.1:8080/actuator/metrics/process.start.time
curl -s http://127.0.0.1:8080/actuator/metrics/process.cpu.usage
curl -s http://127.0.0.1:8080/actuator/metrics/system.cpu.usage
curl -s http://127.0.0.1:8080/actuator/metrics/system.cpu.count
curl -s http://127.0.0.1:8080/actuator/metrics/process.cpu.time
```

Only read load average or file descriptor metrics if those names appear in the list. In PowerShell, where `curl` is an alias, use `curl.exe` to run the curl commands properly. Use `-i` when you need to distinguish HTTP errors from payload content.

**Illustrative** JSON example, not fixed measurements that every run must return:

```json
{
  "name": "process.uptime",
  "baseUnit": "seconds",
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 123.456
    }
  ],
  "availableTags": []
}
```

Read this as "the JVM of the queried instance has been running for about 123.456 seconds." Do not read it as CPU time, host uptime, or the time the entire service has continuously been ready.

## 4. Reading CPU with the Right Ratio and Scope

### 4.1. process.cpu.usage Differs from system.cpu.usage

`process.cpu.usage` reads recent CPU utilization of the JVM process. It includes both application threads and internal threads such as GC/JIT, so high CPU does not by itself point to a specific business method as the cause.

`system.cpu.usage` refers to the operating environment reported by the MXBean source. Depending on JDK and deployment setup, that environment may be the host OS, virtualization, or a container. Do not assume it represents total CPU of the entire host in every setup. [JDK 17 OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html).

When a valid value per the source contract is in 0..1, `0.35` corresponds to roughly 35%. Multiply by 100 for percentage presentation, but do not change the source unit to 35 in every query and then multiply again on the dashboard.

This is a "recent" ratio according to how the system samples, not an instantaneous CPU value at an arbitrary resolution chosen by the reader. Readings taken too close together may add no information; a single reading right after startup is also insufficient to conclude steady-state load.

### 4.2. Low Overall CPU Capacity Usage Does Not Rule Out a Busy Core

`system.cpu.count` uses the number of available processors reported by the JVM. It is not the number of physical CPUs/sockets on the motherboard, nor is it CPU utilization.

If a process is observed relative to 8 processors of capacity and only one thread runs CPU continuously, process utilization may be roughly 1/8 = 12.5%. This is an example for understanding normalization, not a mandatory exact result for every sample.

A single-threaded processing step can already hit its limit even while process-wide CPU ratio remains low. Combine thread analysis/profiling and latency; do not conclude "CPU still has 87.5% free so the program cannot be CPU-bound."

In containers, also inspect CPU limits/quotas, CPUs the JVM considers available, and platform throttling data. `system.cpu.count` and a single CPU ratio alone are not enough to infer the entire resource allocation mechanism. [Available processors in MXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html).

### 4.3. Unavailable Values Do Not Equal 0%

The management source can return a negative value when CPU usage information is unavailable; Micrometer can also skip registering the metric if it cannot detect a suitable method, or return NaN when reading fails.

Distinguish three situations: **metric name absent**, **meter present but sample invalid/unavailable**, and **valid sample equal to 0**. Do not replace all of them with 0 and announce that the process is idle.

When comparing process CPU with system CPU, match the same instance, time interval, and sample semantics. Non-simultaneous sampling sources can produce snapshots that are hard to compare; do not use a single pair of numbers as absolute reconciliation proof.

## 5. process.cpu.time: Total CPU Time, Not Uptime

In Micrometer **1.13.0**, `ProcessorMetrics` registers `process.cpu.time` using a `FunctionCounter`, with `baseUnit("ns")`. The measurement may appear under statistic `COUNT`, but the quantity being counted is **CPU nanoseconds**, not request count or method invocation count. [ProcessorMetrics 1.13.0 source](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/system/ProcessorMetrics.java).

For example, `process.cpu.time = 4,000,000,000 ns` is 4 seconds of cumulative CPU time. Do not read it as 4 billion seconds, and do not treat the `COUNT` statistic as 4 billion business events.

CPU time sums CPU time across threads in the process. Multiple threads can run concurrently across multiple cores, so total CPU time can exceed elapsed wall-clock time. Conversely, a JVM doing heavy I/O waiting can have large uptime while CPU time grows slowly.

You can estimate the average number of CPU cores used from two compatible snapshots:

```text
average CPU cores used
  ≈ delta CPU time (ns) / [delta wall-clock time (s) × 1,000,000,000]

Example:
  CPU time increases by 4,000,000,000 ns in 2 real seconds
  => on average about 2 CPU cores
```

If the true reference capacity is 4 cores under the same normalization, that figure corresponds to about 50%. However, do not claim a manual formula always matches `process.cpu.usage` exactly: sampling intervals, container limits, and how the OS source computes it can differ.

Only take differences from the same process over the same lifecycle, using verified units and discarding invalid samples. After a JVM restart, total CPU time does not simply continue from the old process.

## 6. Uptime and Start Time

### 6.1. process.uptime Is the Age of the Running JVM

`process.uptime` originates from `RuntimeMXBean.getUptime()`. The Java source returns milliseconds; `UptimeMetrics` uses a `TimeGauge` so the registry converts to the appropriate unit. With the example's SimpleMeterRegistry, the value is emitted in seconds. [UptimeMetrics 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/system/UptimeMetrics.java).

Rising uptime does not prove the API is able to serve requests. A process can still be alive while threads are stuck, overloaded, unable to reach dependencies, or not yet ready for traffic. Health/readiness data, request outcomes, and latency are needed to evaluate those questions.

Low uptime can result from a restart, deploying a new instance, or reading a different instance. A single read through a load balancer does not tell you "the uptime of the entire service."

### 6.2. process.start.time Is a Timestamp, Not a Duration

`process.start.time` originates from `RuntimeMXBean.getStartTime()`: the approximate time the JVM started since the Unix epoch. The Java source uses milliseconds, while TimeGauge output depends on the registry unit. [RuntimeMXBean: uptime and start time](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/RuntimeMXBean.html).

For example, if `baseUnit=seconds` and the value is 1,700,000,000, that is a point in time, not a JVM that has been running for 1.7 billion seconds. This illustrative value corresponds to `2023-11-14T22:13:20Z`.

```java
double epochSeconds = 1_700_000_000.0;
java.time.Instant startedAt =
    java.time.Instant.ofEpochMilli((long) (epochSeconds * 1000));
System.out.println(startedAt);
// 2023-11-14T22:13:20Z
```

The snippet above only illustrates conversion after verifying the unit is seconds. Do not multiply by 1,000 again if the source data is already in milliseconds. When presenting to viewers, convert the timezone explicitly; the `Z` suffix denotes UTC.

### 6.3. Combining Signals to Recognize Lifecycle

Tracking uptime together with start time and instance identity helps identify process replacements/restarts. PID can be useful on the machine under investigation, but PIDs can be reused and depend on container namespaces; do not rely on PID alone as a system-wide historical identifier.

JVM uptime is not the time since Spring finished starting: the JVM already existed before the application context finished initializing. Nor is it the operating system's uptime.

## 7. system.load.average.1m Is Not CPU Percentage

Load average is a different load quantity from CPU usage. The MXBean source describes a one-minute average related to runnable entities running on or waiting for processors; exact details depend on the platform. Do not convert `load=2.5` into "250% CPU."

Place it alongside available CPU capacity and signs of resource waiting. A high load value does not by itself tell you what Java threads are doing, and load average does not replace CPU usage or thread analysis.

In binder 1.13.0, this metric is registered only when `getSystemLoadAverage()` returns a non-negative value at binder attachment time. On unsupported platforms, such as many Windows environments, the name may be absent. This is not a requirement to fabricate a dummy value of 0 to complete a list.

## 8. Open Files Are Actually File Descriptors

### 8.1. Not Just Text Files on Disk

On Unix systems, a file descriptor is a numeric handle a process uses to work with I/O resources. Beyond regular files, there are sockets, pipes, and other OS objects. One resource can have multiple descriptors; do not interpret the count as the number of distinct data files.

For example, rising descriptor counts can involve network connections, logs, libraries opening files, or a code path failing to close resources. `process.files.open` only gives a count; it does not return a list of paths or directly point to what holds them. [File descriptors in Linux /proc/pid/fd](https://www.man7.org/linux/man-pages/man5/proc_pid_fd.5.html).

### 8.2. open, max, and Utilization Ratio

- `process.files.open` is the number of descriptors open when the source is read.
- `process.files.max` is the maximum reported by the management source, not the historical peak of open files and not total disk capacity.
- When both have valid data and a meaningful limit, `open / max` can be computed to see the fraction of the limit used.

```text
Hypothetical example:
  open = 800 descriptors
  max  = 1,000 descriptors
  ratio = 800 / 1,000 = 0.8 = 80%
```

Only divide when numbers are finite, open is non-negative, and max is greater than 0. If the source reports a huge or virtually unlimited ceiling, a tiny ratio may not help predict trouble; verify the configured limit and actual growth rate.

Do not clamp ratios to 100% just to hide cases of non-simultaneous data or changing limits. Before choosing alert thresholds, check source semantics, remaining headroom, load variation, and required response time.

The descriptor limit is one kind of resource limit. An application connection pool can still exhaust before the whole process approaches its descriptor limit; conversely, enlarging pools can increase descriptor pressure.

### 8.3. Platform Support Is a Real Precondition

`FileDescriptorMetrics` 1.13.0 looks for suitable methods on the Unix operating system MXBean. It only registers the gauges for which the corresponding method is available. [FileDescriptorMetrics 1.13.0 source](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/system/FileDescriptorMetrics.java).

Therefore, when moving from Linux to Windows/another JDK, `process.files.open` or `process.files.max` may not appear. Missing metrics do not prove 0 files are open, nor do they prove the JVM or Actuator is broken. Do not equate these metrics with Windows handle counters.

Even on Unix environments, check the actual bean/methods, permissions, and JDK. The Java contract specifically provides open/max descriptor counting methods via `UnixOperatingSystemMXBean`. [JDK 17 UnixOperatingSystemMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/UnixOperatingSystemMXBean.html).

### 8.4. Read Trends Instead of Concluding a Leak from One Point

Descriptor counts can rise during pool initialization, library loading, or traffic increases and then stabilize. A signal worth investigating is sustained growth across multiple similar load cycles, failing to return to a reasonable baseline, or steadily shrinking remaining headroom.

That trend is evidence to investigate, not proof by itself of a specific leak site. Cross-check resource types, reference/connection retention paths, and resource closing behavior. When writing code that owns streams/channels, use proper closing mechanisms such as try-with-resources; do not try to exhaust descriptors to "verify" on a live serving system.

## 9. Java 17+ Program to Verify Binders and Units

The following program does not start a web server. It binds the three binders directly to `SimpleMeterRegistry`, prints data from the running JVM itself, and verifies the statistic/unit of present metrics. It does not fabricate fixed CPU figures or simulate file descriptor support for unsupported platforms.

Create a Gradle project with a wrapper and JDK 17 available:

```text
process-metrics-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat and gradle/wrapper/
  src/main/java/ProcessMetricsDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'process-metrics-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'ProcessMetricsDemo'
}
```

Versions are pinned to verify the API. In an actual Boot project, keep Micrometer versions managed by Boot's compatible dependency management.

`src/main/java/ProcessMetricsDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Statistic;
import io.micrometer.core.instrument.binder.system.FileDescriptorMetrics;
import io.micrometer.core.instrument.binder.system.ProcessorMetrics;
import io.micrometer.core.instrument.binder.system.UptimeMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class ProcessMetricsDemo {

    private record Expected(String name, Statistic statistic, String unit) {
    }

    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            new ProcessorMetrics().bindTo(registry);
            new UptimeMetrics().bindTo(registry);
            new FileDescriptorMetrics().bindTo(registry);

            System.out.println("pid=" + ProcessHandle.current().pid());

            List<Expected> expected = List.of(
                new Expected("process.uptime", Statistic.VALUE, "seconds"),
                new Expected("process.start.time", Statistic.VALUE, "seconds"),
                new Expected("process.cpu.usage", Statistic.VALUE, null),
                new Expected("process.cpu.time", Statistic.COUNT, "ns"),
                new Expected("system.cpu.count", Statistic.VALUE, null),
                new Expected("system.cpu.usage", Statistic.VALUE, null),
                new Expected("system.load.average.1m", Statistic.VALUE, null),
                new Expected("process.files.open", Statistic.VALUE, "files"),
                new Expected("process.files.max", Statistic.VALUE, "files")
            );

            for (Expected item : expected) {
                inspect(registry, item);
            }

            requirePresent(registry, "process.uptime");
            requirePresent(registry, "process.start.time");
            requirePresent(registry, "system.cpu.count");

            double open = readOrNaN(registry, "process.files.open");
            double maximum = readOrNaN(registry, "process.files.max");
            double fraction = fileFraction(open, maximum);
            if (Double.isFinite(fraction)) {
                System.out.printf(Locale.ROOT,
                    "live.fdFraction=%.6f%n", fraction);
            }
            else {
                System.out.println("live.fdFraction=UNAVAILABLE");
            }

            System.out.printf(Locale.ROOT, "example.fdFraction=%.6f%n",
                fileFraction(800, 1000));
            System.out.println("example.invalidLimit="
                + Double.isNaN(fileFraction(800, 0)));
            System.out.println("CONTRACT_PASS");
        }
        finally {
            registry.close();
        }
    }

    private static void inspect(SimpleMeterRegistry registry, Expected expected) {
        Meter meter = registry.find(expected.name()).meter();
        if (meter == null) {
            System.out.println(expected.name() + "=UNAVAILABLE");
            return;
        }
        if (!Objects.equals(meter.getId().getBaseUnit(), expected.unit())) {
            throw new AssertionError("Unexpected unit for " + expected.name());
        }

        for (var sample : meter.measure()) {
            if (sample.getStatistic() != expected.statistic()) {
                throw new AssertionError(
                    "Unexpected statistic for " + expected.name());
            }
            System.out.printf(Locale.ROOT,
                "%s statistic=%s unit=%s value=%.6f%n",
                expected.name(), sample.getStatistic(),
                expected.unit() == null ? "none" : expected.unit(),
                sample.getValue());
        }
    }

    private static void requirePresent(SimpleMeterRegistry registry, String name) {
        if (registry.find(name).meter() == null) {
            throw new AssertionError("Expected baseline metric: " + name);
        }
    }

    private static double readOrNaN(SimpleMeterRegistry registry, String name) {
        Meter meter = registry.find(name).meter();
        if (meter != null) {
            for (var sample : meter.measure()) {
                return sample.getValue();
            }
        }
        return Double.NaN;
    }

    private static double fileFraction(double open, double maximum) {
        if (!Double.isFinite(open) || !Double.isFinite(maximum)
                || open < 0 || maximum <= 0) {
            return Double.NaN;
        }
        return open / maximum;
    }
}
```

Run from the project directory:

```bash
./gradlew -q run --console=plain
```

On Windows PowerShell use `.\gradlew.bat -q run --console=plain`. Gradle resolves dependencies and runs main. If using `javac`/`java` directly, the classpath needs Micrometer and its resolved dependencies in both steps.

### 9.1. A Verified Output

This is a **real snapshot from a run on Windows/JDK 17**, not values that another machine or subsequent run must repeat. PID, start time, CPU count, and CPU/uptime samples depend on the environment:

```text
pid=65848
process.uptime statistic=VALUE unit=seconds value=0.097000
process.start.time statistic=VALUE unit=seconds value=1793885033.543000
process.cpu.usage statistic=VALUE unit=none value=0.036723
process.cpu.time statistic=COUNT unit=ns value=718750000.000000
system.cpu.count statistic=VALUE unit=none value=28.000000
system.cpu.usage statistic=VALUE unit=none value=0.179431
system.load.average.1m=UNAVAILABLE
process.files.open=UNAVAILABLE
process.files.max=UNAVAILABLE
live.fdFraction=UNAVAILABLE
example.fdFraction=0.800000
example.invalidLimit=true
CONTRACT_PASS
```

The `UNAVAILABLE` lines are printed by the program when a meter is absent or a valid ratio cannot be computed; they are not numeric values that Actuator automatically inserts into JSON. `unit=none` means the ID sets no base unit; the meaning of CPU ratio is still defined by the source contract.

`process.cpu.time` has statistic COUNT and unit ns, matching the referenced binder. The fact that process CPU time can exceed uptime in a snapshot is not an error by itself: threads can consume CPU concurrently and values are also read at slightly different instants.

The lines starting with `example.` use hypothetical numbers to test division, separated from `live.`. They do not claim the live process is using 800/1,000 descriptors.

`CONTRACT_PASS` indicates that present metrics matched the statistic/unit checked by the program and the three baseline metrics `process.uptime`, `process.start.time`, and `system.cpu.count` are present. It does not conclude the system is healthy, CPU is optimal, or every optional metric is supported by the platform.

### 9.2. Why Not Re-Bind These Binders Arbitrarily in a Boot App?

In the standalone program, code creates its own registry, so it binds binders and closes the registry in `finally`. In a Boot app, use the registry/binders managed by the active configuration; do not create a new registry inside a service and expect Boot's endpoint to read it automatically.

This plain Java program also does not expose `/actuator/metrics`. The HTTP commands earlier in the lesson apply to a Boot web application with configured endpoints, whereas this program verifies sources and measurement contracts without needing a network port.

## 10. Combining Signals to Ask the Next Question

| Observed Signal | Grounded Investigation Path | Cannot Immediately Conclude |
| --- | --- | --- |
| Sustained high process CPU, rising latency | Check CPU-consuming threads, GC/JIT, workload, and profiling | A specific controller definitely has an infinite loop |
| Low process CPU but high environment CPU | Check resource contention and environment measurement scope | The JVM is definitely unaffected |
| Low total CPU ratio but one thread always busy | Check single-thread bottlenecks/parallelism | The whole processing pipeline still has plenty of usable capacity |
| Low uptime or changed start time | Verify instance lifecycle, deployments, restarts, and logs | The old process definitely crashed from an application bug |
| Open descriptors rising across load bursts and nearing limit | Check retained connections/files, closing rules, and OS limits | The exact leak location is already known |
| File metrics or load average absent | Check platform/JDK, binder capabilities, and filters | The true value of the quantity is 0 |

These inferences require time series and context. A single endpoint read gives a snapshot; viewing trends, correlations, and alerting requires an appropriate collection/historical storage system.

Do not sum uptimes of multiple JVMs into "service uptime." Do not take a simple average of CPU across instances with different CPU capacities and treat it as cluster-wide utilization. Nor should you sum open/max percentages across processes to infer a combined percentage while ignoring different limits.

## 11. When Data Looks Unexpected

1. **Confirm exact name, instance, port, and access permissions.** An HTTP 404 for an unregistered name differs from inability to access the list endpoint.
2. **Check the actual registry and binders.** Is metrics infrastructure present with the matching binder, or are two separate registries being written and read?
3. **Check filters and meter acceptance configuration.** Exposing the endpoint does not bypass a filter that denied a metric name.
4. **Verify JVM/OS capabilities.** Especially for load average, extended CPU, and file descriptors.
5. **Read units/statistics before transforming.** CPU time ns is not seconds, uptime is not a timestamp, and COUNT is not always an event count.
6. **Distinguish missing/invalid data from 0.** Do not fabricate placeholder zeros to make charts look complete.
7. **Align timestamps and lifecycle.** Restarts, instance replacements, and CPU/descriptor limit changes alter interpretation.

Do not rush to add broad reflection permissions or build a custom gauge reading other OS information just because a name is missing. First check which interfaces the binder supports and whether the information source actually exists in the running environment.

## 12. Self-Check

1. Does `process.cpu.usage=0.25` allow saying the JVM uses exactly one quarter of one core? What else must you know about normalization?
2. `process.cpu.time` increases by 6 billion ns over 3 real seconds. Estimate the average number of cores used and state the conditions for comparing against a CPU ratio.
3. The same response contains `process.uptime` in seconds and `process.start.time` in epoch seconds. Explain why the two numbers have vastly different magnitudes.
4. Uptime rises steadily, yet health/readiness reports not ready. Why are those pieces of information not contradictory?
5. A Windows machine does not have `process.files.open`. Which situations must be distinguished before putting "0 open files" on a dashboard?
6. If open=900 and max=1,000, what is the utilization ratio? If max=0 or the data is non-finite, how must it be handled?
7. How does descriptor count rising after startup and then stabilizing differ from rising steadily across multiple load cycles? Name additional evidence needed to conclude an unclosed resource.
8. Why does `process.files.max` typically have statistic VALUE, whereas `process.cpu.time` can have statistic COUNT without being a request counter?

Reading this metric group effectively means keeping **process/environment scope, time semantics, units, and platform capability** clear, then using combined signals to investigate rather than concluding from a single number.

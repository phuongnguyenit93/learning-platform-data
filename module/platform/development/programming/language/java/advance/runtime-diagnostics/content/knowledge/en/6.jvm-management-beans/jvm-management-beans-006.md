# 6.6 — Checking support, enabled state, and unavailable values of MXBean metrics

## 1. Why check before reading metrics?

Java's Platform MXBeans help observe threads, heap, garbage collection (GC), JIT compilation, and runtime via `java.lang.management`. Yet **the existence of a getter does not mean a measurement is always supported, enabled, or available** on the current JVM.

For example, `ThreadMXBean.getCurrentThreadCpuTime()` can return `-1` when monitoring is disabled; `MemoryUsage.getMax()` can be `-1` because the memory limit is undefined; `MemoryPoolMXBean.getUsage()` can return `null` when a pool is no longer valid. Conversely, `0` can be a valid measurement: 0 GCs, 0 threshold crossings, 0 bytes, or 0 recorded time.

Lesson goals:

1. Check **supported**: does the JVM provide this measurement?
2. Check **enabled**: is measurement turned on (if the API has an enabled state)?
3. Check **available**: is the sample just read actually valid per the method's contract?
4. Distinguish a valid `0` from `-1`, special negative values, `null`, missing beans, and exceptions.
5. Design logs, metrics, and dashboards that never turn "unknown" into "zero".

> **Principle:** Check capability and state first; read the value only when appropriate; interpret sentinels per **each specific API**. Never convert unavailable values into 0.

## 2. State model for a measurement

```text
Identify the JVM/MXBean to query
    |
    +-- Bean / attribute missing        → NOT_PRESENT
    +-- Connection or permission error  → READ_ERROR
    |
    +-- If API has is...Supported():
    |      false                        → UNSUPPORTED
    |      true                         → continue
    |
    +-- If API has is...Enabled():
    |      false                        → DISABLED
    |      true                         → continue
    |
    +-- Read getter and apply API contract:
           null / -1 / negative N/A     → UNAVAILABLE or UNDEFINED
           0 or valid number            → AVAILABLE
```

This is a **classification model for diagnostic applications**, not a built-in Java enum.

| State | Meaning | Example | What to do |
| --- | --- | --- | --- |
| `UNSUPPORTED` | JVM does not support the measurement capability | `isThreadContentionMonitoringSupported() == false` | Do not call dependent operations; use another source |
| `DISABLED` | Supported, but monitoring/threshold is turned off | `isThreadCpuTimeEnabled() == false` | Record state; do not treat as value 0 |
| `UNAVAILABLE` | Measurement permitted, but no meaningful sample at read time | `getThreadCpuTime(id) == -1` when thread ended | Discard sample; keep state and reason if known |
| `UNDEFINED` | An attribute is not defined by the runtime | `MemoryUsage.getMax() == -1` | Do not compute ratios needing that denominator |
| `AVAILABLE` | Getter returns a valid value | GC count `0` or non-negative CPU time | Store value with unit/timestamp |
| `NOT_PRESENT` | Bean/attribute is not exposed | `getCompilationMXBean() == null` | Verify interface/JDK/vendor; fall back |
| `READ_ERROR` | Cannot read due to permissions, network, or runtime | JMX connection error, `SecurityException` | Report collection error; do not label unsupported |

**Not every API has all three of supported/enabled/value.** For example, compilation has `isCompilationTimeMonitoringSupported()` without a corresponding `isCompilationTimeMonitoringEnabled()`; GC count uses `-1` to indicate undefined instead of a separate boolean capability. Do not force every MXBean into one rigid mold that misrepresents its status.

### 2.1. Rules for choosing an action

1. Verify the exact JVM instance, timestamp, and access permissions.
2. Query `is...Supported()` when the API provides a capability check.
3. If an `enabled` switch exists, query its state before reading.
4. Read the getter and check `null`/sentinels/value range per Javadoc.
5. Record `value`, `unit`, `state`, `source`, and timestamp—or record the state without a value.
6. Handle exceptions and races: a thread/pool may end between check and read.

An unsupported measurement on JVM A is **not** necessarily a bug on JVM B; conversely, an availability change after a deploy may be a signal worth investigating.

## 3. ThreadMXBean: checking CPU time for the right thread scope

Obtain the standard bean:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

The snippet above is illustrative and belongs inside a method/class. Java 17 has two **distinct** checks:

- `isCurrentThreadCpuTimeSupported()`: CPU time measurement for **the calling thread**.
- `isThreadCpuTimeSupported()`: CPU time measurement for **threads by ID**. If the JVM supports measuring all threads, it also supports the current thread.

`isThreadCpuTimeEnabled()` indicates whether the feature is currently enabled; support and enabled state are **independent**. `isThreadCpuTimeEnabled()` may throw `UnsupportedOperationException` when the JVM supports CPU time measurement for neither the current thread nor other threads, so do not call it before capability checks.

### 3.1. Reading the current thread's CPU time

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
boolean supported = bean.isCurrentThreadCpuTimeSupported();

if (!supported) {
    System.out.println("cpu=UNSUPPORTED");
} else if (!bean.isThreadCpuTimeEnabled()) {
    System.out.println("cpu=DISABLED");
} else {
    long nanos = bean.getCurrentThreadCpuTime();
    System.out.println(nanos < 0 ? "cpu=UNAVAILABLE"
                                 : "cpu=" + nanos + " ns");
}
```

This snippet needs imports and an enclosing method. CPU time measures **executed CPU time**, not total wall-clock latency. Values are expressed in nanoseconds, yet **nanosecond resolution does not imply nanosecond accuracy**.

`getThreadCpuTime(long id)` can return `-1` because the thread is no longer alive/does not exist, the feature is disabled, or no sample exists; it can also throw `UnsupportedOperationException` when measuring other threads is unsupported. Therefore, a single `-1` **cannot pinpoint a unique cause**; cross-check support, enabled state, and thread lifecycle.

### 3.2. Does enabling measurement affect the JVM?

Yes. `setThreadCpuTimeEnabled(true)` can increase measurement overhead on some JVMs, requires management permission, and is a **state mutation**. A read-only probe should not turn on measurement on its own just to get numbers; it requires an operational decision and a record of when measurement began.

When enabled after a thread has already been running for a while, JVMs may pick different accounting start points within the API contract. Do not claim the counter after enabling represents the thread's full lifetime.

## 4. Thread contention: supported, enabled, and -1

`ThreadMXBean` also provides:

```java
bean.isThreadContentionMonitoringSupported();
bean.isThreadContentionMonitoringEnabled();
bean.setThreadContentionMonitoringEnabled(true);
```

This snippet lists the methods; it does not tell you to run the setter. Java 17 specifies that contention monitoring may be unsupported by the JVM and is typically **disabled by default**.

- `isThreadContentionMonitoringSupported() == false` → `UNSUPPORTED`; calling `isThreadContentionMonitoringEnabled()` may throw `UnsupportedOperationException`.
- `supported == true` yet `isThreadContentionMonitoringEnabled() == false` → `DISABLED`.
- Only when enabled can `ThreadInfo.getBlockedTime()` and `getWaitedTime()` reflect cumulative times in **milliseconds**.
- `ThreadInfo.getBlockedTime() == -1` or `getWaitedTime() == -1` when monitoring is disabled **does not mean** negative wait time or "zero contention".

`ThreadMXBean.isObjectMonitorUsageSupported()` and `isSynchronizerUsageSupported()` are two **separate** capabilities when requesting monitor and ownable synchronizer info via `getThreadInfo(...)`/`dumpAllThreads(...)`. Do not infer lock-info support from CPU-time support.

A thread can terminate between fetching IDs and calling `getThreadInfo`. `getThreadInfo(long id)` returns `null` when the thread is dead/non-existent; overloads accepting an ID array can return an array containing `null` elements. This is a **race/lifecycle behavior**, not proof that the JVM lacks ThreadMXBean.

## 5. MemoryPoolMXBean: supported thresholds and enabled thresholds

Each memory pool has distinct capabilities. Key methods:

- `isUsageThresholdSupported()` and `isCollectionUsageThresholdSupported()` check two independent threshold types.
- `getUsageThreshold()`, `getCollectionUsageThreshold()` return thresholds in **bytes**; call only when the corresponding type is supported.
- `setUsageThreshold(...)`, `setCollectionUsageThreshold(...)` are **configuration-mutating** operations.
- `getUsage()`, `getPeakUsage()`, and `getCollectionUsage()` read memory snapshots; check for null and pool validity.

### 5.1. Threshold equal to 0 differs from usage equal to 0

For a **supported** threshold type, `threshold > 0` indicates threshold checking is enabled; `threshold == 0` means **threshold checking is disabled**. This is a rule specific to `MemoryPoolMXBean`, **not** applicable to all other getters.

```java
if (!pool.isUsageThresholdSupported()) {
    System.out.println("threshold=UNSUPPORTED");
} else {
    long threshold = pool.getUsageThreshold();
    System.out.println(threshold == 0
        ? "threshold=DISABLED" : "threshold=ENABLED(" + threshold + " bytes)");
}
```

This snippet requires a `MemoryPoolMXBean pool` variable and method context. Calling `getUsageThreshold()` on an unsupported pool can throw `UnsupportedOperationException`.

**`getUsageThresholdCount() == 0` is not the disabled state**: a pool can have its threshold enabled without ever crossing it. To know whether the feature is enabled, read the threshold setting itself. Likewise, collection usage thresholds have their own capability and setting; do not use usage threshold support as a proxy.

### 5.2. Invalid pools and missing MemoryUsage fields

`pool.isValid()` indicates whether the pool still exists in the JVM. `pool.getUsage()` may return `null` if the pool is no longer valid. Never call `usage.getUsed()` when `usage == null`.

A `MemoryUsage` has four fields:

| Field | Unit | Special-case meaning |
| --- | --- | --- |
| `getInit()` | bytes | `-1` if initial value is undefined |
| `getUsed()` | bytes | Non-negative; `0` can be valid |
| `getCommitted()` | bytes | Non-negative, normally ≥ used |
| `getMax()` | bytes | `-1` if maximum is undefined |

`max == -1` means **UNDEFINED**, distinct from heap max = 0; never compute `used/max` or percent `used` when `max <= 0`. `max` is also not automatically the container limit or process RSS.

```java
MemoryUsage usage = pool.getUsage();
if (usage == null) {
    System.out.println("poolUsage=UNAVAILABLE");
} else {
    long max = usage.getMax();
    System.out.println("poolMax=" +
        (max < 0 ? "UNDEFINED" : max + " bytes"));
}
```

This snippet likewise needs a method and `MemoryUsage` import; it illustrates preserving undefined metadata. `MemoryPoolMXBean.getUsage()` returns an **estimate** at read time and does not prove object retention or a memory leak.

## 6. GC, JIT, and extension MXBeans: each API has its own contract

### 6.1. GarbageCollectorMXBean

`ManagementFactory.getGarbageCollectorMXBeans()` returns the list of collectors exposed by the JVM. For each bean:

- `getCollectionCount()` returns the cumulative counter, or **`-1`** if count is undefined.
- `getCollectionTime()` returns approximate cumulative collection time (milliseconds), or **`-1`** if undefined.

`0` can mean no collections yet, or durations too short to register. Both `0` and `-1` carry distinct meanings; do not merge them. Collector counts/names depend on the JDK and GC algorithm; do not hard-code a name like `G1 Young Generation` into generic measurement logic.

```java
for (GarbageCollectorMXBean gc :
        ManagementFactory.getGarbageCollectorMXBeans()) {
    long count = gc.getCollectionCount();
    System.out.println(gc.getName() + " count=" +
        (count < 0 ? "UNAVAILABLE" : Long.toString(count)));
}
```

This snippet requires imports and an enclosing method. If the bean list is empty, that is a discovery state—**do not** synthesize a `0` counter for an imaginary collector.

### 6.2. CompilationMXBean

`ManagementFactory.getCompilationMXBean()` can return `null` when the JVM has no corresponding compilation system. If the bean exists, `isCompilationTimeMonitoringSupported()` indicates whether compilation time measurement is supported; calling `getTotalCompilationTime()` when unsupported may throw `UnsupportedOperationException`.

There is no general enabled method equivalent to `isThreadCpuTimeEnabled()` for compilation time. `getTotalCompilationTime()` is approximate cumulative time of compilation threads in milliseconds; it is **not** a performance benchmark directly comparable across every JVM vendor.

### 6.3. Extensions in com.sun.management

`com.sun.management.OperatingSystemMXBean` is an extension in the `jdk.management` module. `getProcessCpuLoad()` returns a value in `[0.0, 1.0]` when a sample exists, and a **negative number** if unavailable; `0.0` is a valid value. Do not assume every JVM with the standard `java.lang.management.OperatingSystemMXBean` supports this extension.

`com.sun.management.ThreadMXBean` adds per-thread allocated bytes, with `isThreadAllocatedMemorySupported()`, `isThreadAllocatedMemoryEnabled()`, and `getThreadAllocatedBytes(...)`. Since this is an extension, check the interface/module, capability, enabled state, and method-specific sentinels before using it.

**Do not force a single "-1 sentinel" across every numeric type:** CPU load uses a negative floating-point number, memory max uses -1 undefined, GC count -1 undefined, and thread CPU -1 can mean disabled or dead thread. Each method has its own contract.

## 7. Remote JMX: missing metrics differ from connection errors

Reading MXBeans locally via `ManagementFactory` differs from collecting over a remote JMX endpoint. With remote JMX, even before checking capabilities you must check:

```text
JMX endpoint → connect / authentication / authorization → MBean/attribute
                                                              |
                                         supported → enabled → sample
```

| Response | Likely cause | Proper classification |
| --- | --- | --- |
| Timeout, TLS/credential failure | Cannot connect or authenticate | `READ_ERROR` |
| `InstanceNotFoundException` | Wrong ObjectName, bean unregistered, or disappeared | `NOT_PRESENT` / lifecycle error |
| `AttributeNotFoundException` | Attribute absent from queried interface/runtime | `NOT_PRESENT`; inspect MBeanInfo |
| `SecurityException` / authorization denied | Lacks read permission | `READ_ERROR`, not `UNSUPPORTED` |
| `UnsupportedOperationException` | Operation unsupported by the JVM | `UNSUPPORTED` per API contract |
| Getter returns Javadoc-described sentinel | Missing/undefined sample or object gone | `UNAVAILABLE` / `UNDEFINED` |
| Getter returns `0` within valid range | Measured value is 0 | `AVAILABLE(0)` |

Capability/enable/value checks are usually **separate** reads, not an atomic snapshot. A thread can die or a pool can change between reads; code needs fallbacks and proper read-error handling.

Permissions to enable monitoring are normally higher than read permissions. Never toggle runtime flags, thresholds, or measurement state inside an exporter just because a previous read returned `-1`.

## 8. Java 17+: complete program demonstrating five states

This program both verifies **five synthetic scenarios with deterministic output** and reads **live MXBeans of the running JVM** without modifying monitoring state.

Create the file **`MxBeanCapabilityDemo.java`**:

```java
import java.lang.management.*;

public class MxBeanCapabilityDemo {
    static String classify(boolean supported, boolean enabled, Long value) {
        if (!supported) return "UNSUPPORTED";
        if (!enabled) return "DISABLED";
        if (value == null || value < 0) return "UNAVAILABLE";
        return "AVAILABLE(" + value + ")";
    }

    public static void main(String[] args) {
        System.out.println("fixture.unsupported=" + classify(false, false, -1L));
        System.out.println("fixture.disabled=" + classify(true, false, 0L));
        System.out.println("fixture.unavailable=" + classify(true, true, -1L));
        System.out.println("fixture.zero=" + classify(true, true, 0L));
        System.out.println("fixture.positive=" + classify(true, true, 42L));

        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        boolean cpuSupported = threads.isCurrentThreadCpuTimeSupported();
        boolean cpuEnabled = cpuSupported && threads.isThreadCpuTimeEnabled();
        Long cpuNs = cpuEnabled ? threads.getCurrentThreadCpuTime() : null;
        System.out.println("live.threadCpuNs=" +
            classify(cpuSupported, cpuEnabled, cpuNs));

        boolean contentionSupported = threads.isThreadContentionMonitoringSupported();
        boolean contentionEnabled = contentionSupported
            && threads.isThreadContentionMonitoringEnabled();
        System.out.println("live.contention=" +
            (contentionSupported ? (contentionEnabled ? "ENABLED" : "DISABLED")
                                 : "UNSUPPORTED"));

        CompilationMXBean compilation = ManagementFactory.getCompilationMXBean();
        boolean jitSupported = compilation != null
            && compilation.isCompilationTimeMonitoringSupported();
        Long jitMs = jitSupported ? compilation.getTotalCompilationTime() : null;
        System.out.println("live.jitTimeMs=" +
            classify(jitSupported, true, jitMs));

        MemoryUsage heap = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        System.out.println("live.heapMax=" +
            (heap.getMax() < 0 ? "UNDEFINED" : heap.getMax() + " bytes"));

        for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
            boolean supported = pool.isUsageThresholdSupported();
            String state = !supported ? "UNSUPPORTED"
                : pool.getUsageThreshold() == 0 ? "DISABLED" : "ENABLED";
            System.out.println("live.pool[" + pool.getName() + "].threshold=" + state);
        }

        for (GarbageCollectorMXBean gc : ManagementFactory.getGarbageCollectorMXBeans()) {
            long count = gc.getCollectionCount();
            System.out.println("live.gc[" + gc.getName() + "].count=" +
                (count < 0 ? "UNAVAILABLE" : Long.toString(count)));
        }
    }
}
```

Compile and run:

```bash
javac --release 17 MxBeanCapabilityDemo.java
java MxBeanCapabilityDemo
```

**First five stdout lines are exact and fixed:**

```text
fixture.unsupported=UNSUPPORTED
fixture.disabled=DISABLED
fixture.unavailable=UNAVAILABLE
fixture.zero=AVAILABLE(0)
fixture.positive=AVAILABLE(42)
```

The `live.*` lines print **afterward** and vary by JVM vendor, GC, monitor state, and sampling time. Do not hard-code CPU time numbers, JIT time, heap max, pool counts, or collector names.

Explanation of output groups:

- `live.threadCpuNs=AVAILABLE(n)`: current-thread CPU time is supported and enabled, returning non-negative nanoseconds at read time.
- `live.threadCpuNs=DISABLED`: capability exists, yet monitoring is turned off. Does not mean CPU time is actually 0.
- `live.contention=DISABLED`: contention monitoring is off; `blockedTime`/`waitedTime` may be -1.
- `live.jitTimeMs=UNSUPPORTED`: compilation bean is absent or compilation time measurement is unsupported. In real apps, store **NOT_PRESENT** separately if the bean is null.
- `live.heapMax=UNDEFINED`: maximum is undefined; do not compute memory usage percentage against max.
- `live.pool[...].threshold=UNSUPPORTED`: that specific pool does not support a usage threshold, even if other pools do.
- `live.gc[...].count=0`: a real counter value of 0, not missing.

The code was compiled with `javac --release 17` and run successfully on an OpenJDK JVM. The five fixture lines match the output above exactly. This sample only reads and observes; it does not call `setThreadCpuTimeEnabled`, `setThreadContentionMonitoringEnabled`, or `setUsageThreshold`.

**Limitations of the `classify` helper:** it is designed for non-negative integers with a negative sentinel. Other cases such as threshold = 0, `MemoryUsage.getMax() == -1`, and JMX errors must be handled with dedicated logic per the API contract rather than forcing everything into one generic function.

## 9. Metric design: preserving state, unit, and instance

An observation record should preserve: metric name, API source, timestamp, JVM instance (host/container/PID/start time), value when present, unit, and state.

```text
metric: jvm.thread.cpu.time
timestamp_utc: 2026-10-29T09:15:00Z
instance: orders-api/pod-abc/app
source: ThreadMXBean.getCurrentThreadCpuTime
state: AVAILABLE
value: 12345678
unit: ns
```

This is an **illustrative record**, not demo output. If a sample is absent, record a state like `UNAVAILABLE` or `READ_ERROR` and **do not emit value=0**. In Prometheus/exporters, you can omit the numeric sample when missing while exporting a separate low-cardinality health/availability state.

### 9.1. Numeric data rules

- Valid `0` values must be preserved; never use "falsy" checks that discard them.
- `-1` or negative sentinel values must be filtered **before** computing averages, percentages, rates, or percentiles.
- Compute `used/max` only when `max > 0` and both values share the same semantics/unit.
- Convert CPU time nanoseconds to seconds via `ns / 1_000_000_000.0` **after** validating the sample; CPU time differs from wall-clock duration.
- For cumulative GC counters, compute rates only from the difference between two valid samples of the same instance and time window. Counters may reset after restarts.
- Never stuff raw exception stacks, user IDs, thread IDs, or arbitrary request names into metric labels; avoid unbounded time-series cardinality.
- Separate **scrape/read errors** from "valid runtime that does not support the feature"; a green dashboard showing 0 when the exporter actually failed is misleading.

### 9.2. Enabling measurement is an operational change

Setters like `setThreadCpuTimeEnabled`, `setThreadContentionMonitoringEnabled`, `setUsageThreshold`, or `setCollectionUsageThreshold` may require authorization and add overhead. Before enabling, document the investigative question, start time, impact, verification of enabled state, and rollback plan. Never assume cumulative counters contain history from before the feature was enabled.

## 10. Common diagnostic scenarios

### A. Dashboard reports CPU time = 0 for every thread

Check whether the exporter converts `getThreadCpuTime(id) == -1` into zero. Verify support for **any-thread** (distinct from current-thread), enabled state, and thread lifetime. If measurements are missing, display `DISABLED` or `UNAVAILABLE`; consult process CPU/JFR metrics to investigate further.

### B. Memory threshold never fires an alert

Check the exact pool and threshold type: `isUsageThresholdSupported` vs. `isCollectionUsageThresholdSupported`. If support is false → UNSUPPORTED; if threshold = 0 → DISABLED. If threshold > 0 → check crossing events, listeners, windows, and permissions. **Count = 0 does not prove monitoring is disabled.**

### C. Heap usage percent suddenly goes negative

If `getMax() == -1`, dividing `used / max` produces nonsense ratios. Report `UNDEFINED` for the denominator; you can still report `used` or `committed` in bytes. To report a percentage, pick a valid, clearly defined denominator—never arbitrarily substitute `committed` for `max`.

### D. GC counter stays 0 after deployment

`0` can be completely valid if no collections occurred for that collector. Check the collector name and JVM uptime. If count == -1, it is undefined, not zero. Comparing rates across restarts requires identifying the new instance.

### E. Contention time is -1 while latency climbs

`getBlockedTime`/`getWaitedTime` equal -1 when contention monitoring is off. Check `isThreadContentionMonitoringSupported()` and `isThreadContentionMonitoringEnabled()`. If evidence is needed immediately, use thread dumps or JFR as appropriate, then decide on enabling monitoring via operational procedure.

### F. After a JDK upgrade, a metric disappears

Check runtime version, collector/pool names, MBean registration, `com.sun.management` extension presence, enabled state, JMX authorization, and attribute mapping. Only after distinguishing NOT_PRESENT, UNSUPPORTED, and READ_ERROR should you choose a fallback or update the exporter.

## 11. Testing state-handling logic

Separate classification logic from live MXBean calls. A unit test should cover these fixtures:

| supported | enabled | raw | Expected |
| --- | --- | --- | --- |
| false | false | -1 | `UNSUPPORTED` |
| true | false | 0 | `DISABLED` |
| true | true | -1 | `UNAVAILABLE` |
| true | true | null | `UNAVAILABLE` |
| true | true | 0 | `AVAILABLE(0)` |
| true | true | 42 | `AVAILABLE(42)` |

Five fixtures with `Long` values are executed in the demo; the `null` case is handled by `value == null`. Write separate tests for other APIs: threshold 0 is DISABLED, heap max -1 is UNDEFINED, negative CPU load is UNAVAILABLE, and remote read exceptions are READ_ERROR.

Integration tests should exercise differences across JVM vendors/OSes/GC collectors, read permissions, invalid pools, and terminated threads. Never assert a fixed `live.*` value or assume the same memory pool names are always present. Also verify the probe never invokes setters on its own.

## 12. Common mistakes

| Mistake | Why it is wrong | Correct practice |
| --- | --- | --- |
| "If the getter exists, it can be measured." | Some capabilities are optional. | Query `is...Supported` before calling. |
| "Supported means enabled." | Measurements/thresholds have separate enabled states. | Query enabled or threshold value. |
| "`-1` means no activity." | `-1` is an unavailable/undefined sentinel. | Preserve state; do not convert to 0. |
| "`0` means metric missing." | It can be a valid measurement. | Preserve `AVAILABLE(0)`. |
| "Threshold count=0 means disabled." | It can be enabled without having crossed yet. | Read the threshold setting itself. |
| "Compilation bean cannot be null." | JVM may not provide one. | Check null before checking support. |
| "ThreadInfo always returns an object." | Thread may have terminated. | Check null for each ID. |
| "MemoryUsage always has positive max." | Max can be undefined (`-1`). | Check before dividing. |
| "JMX timeout = JVM unsupported." | It is a transport/permission error. | Tag `READ_ERROR` separately. |
| "CPU time is wall-clock latency." | Two different measurement concepts. | Attach units and semantics. |
| "Every collector/VM has the same MXBean extensions." | Depends on vendor/JDK/GC. | Discovery and fallbacks. |
| "Check and read are atomic." | State can change between two calls. | Accept races; handle exceptions. |
| "Read-only probe may auto-enable counters." | Setters mutate state and overhead. | Enable only when authorized. |

## 13. Checklist for monitoring code

- [ ] Verify the exact JVM instance, runtime session, and MXBean source.
- [ ] Check whether the bean/attribute exists and is readable; separate transport/permission errors.
- [ ] Check `supported` whenever the API provides a capability check.
- [ ] Check `enabled` or `threshold > 0` **if** the API has an enabled concept.
- [ ] Read only appropriate getters; handle `null`, `-1`, and negative sentinels per the specific Javadoc.
- [ ] Preserve `0` as a valid value when permitted by the contract.
- [ ] Do not compute percentages/rates if a sample or denominator is missing.
- [ ] Respect ns/ms/bytes units and cumulative counter resets across restarts.
- [ ] Never auto-enable measurement or alter thresholds in a read-only probe.
- [ ] Design low-cardinality availability states for metrics/dashboards.
- [ ] Test fixtures covering all states and test on all supported real JVMs.
- [ ] Record timestamps and explanations for any N/A samples.

## 14. Official Java SE 17 documentation

- [ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): CPU time, contention capability/enabled, thread info.
- [ThreadInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): blocked/waited time and -1 sentinel.
- [MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): usage threshold and collection threshold, isValid, null usage.
- [MemoryUsage](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): init/used/committed/max, undefined sentinel.
- [GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): undefined GC count/time.
- [CompilationMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/CompilationMXBean.html): optional JIT compilation time.
- [ManagementFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): accessing platform MXBeans.
- [com.sun.management.OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): process CPU load and negative values when unavailable.

**Key takeaway:** The order for reading MXBean metrics is **right bean and permissions → supported → enabled (when present) → valid value → interpret by unit and time**. Having no value does not mean 0; a valid 0 does not mean disabled. Explicit states make dashboards reflect what the JVM actually knows.
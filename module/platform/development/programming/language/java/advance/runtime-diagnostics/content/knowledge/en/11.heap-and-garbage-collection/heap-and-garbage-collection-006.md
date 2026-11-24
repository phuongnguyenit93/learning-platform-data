# 11.6 Using GC.heap_info, MXBeans, and jstat to cross-check heap status

## 1. Goal and approach

When a Java process uses a lot of memory, a single "heap in use" number cannot answer key questions: how far has the heap been allocated, is it climbing continuously, is GC reclaiming memory, or are we confusing the heap with metaspace/native memory? This lesson shows how to **cross-check three views of the same JVM**:

1. `jcmd <PID> GC.heap_info`: an instantaneous snapshot of the heap as presented by HotSpot and the active collector.
2. `MemoryMXBean` and `MemoryPoolMXBean`: memory measurements obtained directly inside the JVM or via JMX; convenient for timestamping and monitoring within an application.
3. `jstat`: consecutive statistical samples of memory regions and GC counts/times; useful for explaining changes between two snapshots.

The example scope is **HotSpot JDK 17 or later**, illustrated with G1 GC. Region names, output layouts, and some counters may differ in other collectors, JDK versions, or JVMs. You should not require all three tools to report **the exact same byte count** at different instants; the goal is to verify consistency in *meaning and trend*.

## 2. Understand the quantities accurately before comparing

`MemoryUsage` returns four values in **bytes**:

| Property | Meaning | How to read properly |
| --- | --- | --- |
| `init` | Initial size requested by the JVM, if defined | Related to `-Xms`, but do not treat it as "memory currently occupied". |
| `used` | Bytes currently containing objects/data accounted to the memory region | For heap, includes objects not yet reclaimed by GC; **not synonymous with live object volume**. |
| `committed` | Bytes the JVM has committed and made ready for use by that region | Usually greater than or equal to `used`; can remain high after GC. |
| `max` | Maximum limit the memory region can use if defined | May be `-1` when undefined; not process RSS. |

Unit conversions: `1 KiB = 1,024 bytes`, `1 MiB = 1,048,576 bytes`. `jstat -gc` reports space sizes in **KB (effectively scaled by 1,024 bytes)**, whereas MXBeans report bytes; `jstat -gcutil` reports **percentage utilization of each space**. Times `YGCT`, `FGCT`, and `GCT` are in **seconds**, while `GarbageCollectorMXBean.getCollectionTime()` is in **milliseconds**, if supported by the JVM.

Distinguish three commonly mixed-up ratios:

- **Committed heap utilization**: `heap.used / heap.committed`.
- **Utilization against configured limit**: `heap.used / heap.max`, computed only when `max > 0`.
- **Single-space utilization** (such as the `O` column in `jstat -gcutil`): `old.used / old.capacity`. The `O` column **is not the utilization percentage of the entire heap**.

The heap is where ordinary Java objects and arrays are allocated. Metaspace, compressed class space, code cache, and many other regions belong to **non-heap/native**. Actual process RAM (RSS/working set) also includes thread stacks, direct buffers, native allocations, mapped files, and more, so it **must not** be derived by adding `heap.used` and `metaspace.used`.

## 3. What question does each tool answer?

| Source | What to observe | Question it helps answer | Limitations |
| --- | --- | --- | --- |
| `GC.heap_info` | Heap total/used, region or generation layout, and some metaspace info depending on GC | "At this moment, how is the heap structured and used?" | Output depends on collector/JDK; a single snapshot shows no trend; diagnostic operations have cost. |
| `MemoryMXBean.getHeapMemoryUsage()` | Heap `used`, `committed`, `max` | "How many bytes of heap does the application see as used/committed/max allowed?" | Instantaneous measurement that can change while running; `used` is not post-GC live set. |
| `MemoryPoolMXBean.getUsage()` | Usage of each `HEAP` or `NON_HEAP` pool | "Which region contributes to usage?" | Pool list depends on collector; `getUsage()` may return `null` for pools no longer valid. |
| `jstat -gc` | `EU`, `OU`, survivor usage/capacity, `YGC`, `FGC`, GC times | "How are spaces and GC counters changing?" | Columns/interpretation depend on HotSpot and version; sampled data, not simultaneous with MXBeans. |
| `jstat -gcutil` | `E`, `O`, `S0`, `S1` as %, plus GC counters | "Is each region's utilization rising/falling and did GC run between samples?" | Per-region %, not % of heap; do not parse output as a long-term protocol. |

**Cross-check rule:** confirm **same PID, same JVM, same memory region type, same unit, and same timestamp** before concluding that two numbers disagree.

## 4. Creating a JVM to practice on JDK 17+

Save the following code as exact file `HeapDiagnosticsDemo.java`. The program prints its PID, allocates many short-lived objects, and keeps a small set of objects in `RETAINED` so heap/GC changes are easy to observe. Measured values depend on machine and runtime timing, so there is no fixed numeric stdout.

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Locale;

public final class HeapDiagnosticsDemo {
    private static final Deque<byte[]> RETAINED = new ArrayDeque<>();

    private static String size(long bytes) {
        return bytes < 0
                ? "undefined"
                : String.format(Locale.ROOT, "%.1f MiB", bytes / 1_048_576.0);
    }

    private static void printUsage(String label, MemoryUsage usage) {
        if (usage == null) {
            System.out.println(label + ": unavailable");
            return;
        }
        System.out.printf(Locale.ROOT,
                "%s: used=%s, committed=%s, max=%s%n",
                label, size(usage.getUsed()),
                size(usage.getCommitted()), size(usage.getMax()));
    }

    private static void snapshot() {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        printUsage("Heap", memory.getHeapMemoryUsage());
        printUsage("Non-heap", memory.getNonHeapMemoryUsage());

        for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
            if (pool.getType() == MemoryType.HEAP) {
                printUsage("  " + pool.getName(), pool.getUsage());
            }
        }
        for (GarbageCollectorMXBean gc : ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.printf(Locale.ROOT,
                    "GC %s: collections=%d, timeMs=%d%n",
                    gc.getName(), gc.getCollectionCount(), gc.getCollectionTime());
        }
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID: " + ProcessHandle.current().pid());
        for (int second = 1; second <= 120; second++) {
            for (int i = 0; i < 16; i++) {
                byte[] block = new byte[128 * 1024];
                block[0] = (byte) second;
                if (i % 4 == 0) {
                    RETAINED.addLast(block);
                    if (RETAINED.size() > 32) {
                        RETAINED.removeFirst();
                    }
                }
            }
            if (second % 10 == 0) {
                System.out.println("--- t=" + second + "s ---");
                snapshot();
            }
            Thread.sleep(1_000);
        }
    }
}
```

Compile and run in the **first terminal** (requires a JDK, not just a JRE):

```bash
javac HeapDiagnosticsDemo.java
java -Xms64m -Xmx128m -XX:+UseG1GC HeapDiagnosticsDemo
```

The first line looks like `PID: 12345` (the actual number will differ). Every 10 seconds, the program prints `--- t=10s ---`, `--- t=20s ---`, ... followed by `Heap`, `Non-heap`, heap pools, and GC counters. `-Xms64m` sets the configured initial heap size and `-Xmx128m` sets the heap limit for this experiment; they do not fix `used`. The loop runs for about two minutes; object creation can cause `YGC` to increase, though **the exact GC count is not guaranteed**.

In the **second terminal**, locate the process:

```bash
jcmd -l
```

Use the PID printed by the application; the commands below use **12345 as an illustrative PID**, which must be replaced with the real PID. Run on the same machine/namespace as the JVM under an account permitted to access the process. In containers, the PID seen from the host and inside the container may differ; `jps`/`jcmd -l` cannot always see processes in other namespaces.

## 5. View 1 — `GC.heap_info` snapshot

```bash
jcmd 12345 GC.heap_info
```

On HotSpot with G1, the output usually contains a heap section like `garbage-first heap`, with `total`, `used`, region size, and possibly a `Metaspace` section. **Read the actual labels of the running version**; do not hard-code output lines/units into a parser. With other collectors, line names and structures may differ.

How to read it:

1. `total` helps gauge the heap capacity currently allocated to the JVM at the time of the snapshot (related to `committed`, though not assumed byte-for-byte identical).
2. `used` indicates utilization at the snapshot; the heap can change immediately after the command runs.
3. If `Metaspace` appears, that is **off-heap** information; do not add it to `heap.used`.
4. There is no basis to conclude a leak just because `total` is near `-Xmx` or a single snapshot has high `used`: consider workload and usage **after GC cycles**.

`GC.heap_info` is a diagnostic command whose impact HotSpot documentation classifies as **Medium**. It is not a command requesting a Full GC. Do not substitute `GC.run` to "make numbers look cleaner", because forcing GC alters the phenomenon under investigation.

If you need to know which flags the JVM received, you can also run `jcmd 12345 VM.command_line`; flags and collector selection help explain differences in pools/output.

## 6. View 2 — `MemoryMXBean` and `MemoryPoolMXBean`

In the example, `snapshot()` reads two levels:

- **Whole heap:** `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage()`. This is the preferred metric when comparing total `used/committed/max` in bytes.
- **Individual heap pools:** filter `pool.getType() == MemoryType.HEAP`, then call `pool.getUsage()`. Names like `G1 Eden Space`, `G1 Survivor Space`, and `G1 Old Gen` are G1 examples; do not write code assuming those exact names always exist.

Per the `MemoryMXBean` specification, whole-heap `used` and `committed` are the sum of the values from the **heap pools**, whereas `init` and `max` reflect whole-heap configuration/limits and **do not necessarily equal the sum of pool init/max**. Do not add `Non-heap` into this sum. Some pools may return `null`; the example checks for that case.

If you need to inspect usage after the most recent collection, `MemoryPoolMXBean.getCollectionUsage()` (when non-`null`) provides measurements *after a collection affecting that pool*; it **does not trigger GC** and **is not necessarily a simultaneous snapshot** with `getUsage()`. Do not treat it as the "exact live set" or rely on it when unsupported by the JVM.

The `GarbageCollectorMXBean` list in the example reports total collection counts and cumulative times provided by each collector. `-1` means the counter is undefined. Collector names and event grouping can differ from `YGC/FGC` in `jstat`; use these counters to support trend analysis rather than matching numbers mechanically.

Because MXBean calls execute sequentially, even the `Heap` and pool lines within the same printout can drift slightly due to allocations/GC in between. You can sample externally via JMX, but keep a consistent sampling cadence and consider connection cost and security.

## 7. View 3 — sampling with `jstat`

While the program is running, execute:

```bash
jstat -gc 12345 1000 5
jstat -gcutil -t 12345 1000 5
```

`1000` is the interval of **1,000 ms**; `5` is the sample count. `-t` adds a `Timestamp` column (seconds since JVM startup, **not wall-clock hour-minute-second**). You can run `jstat -gccapacity 12345 1000 5` to view generation/space capacities, if the collector exposes those quantities.

Important columns in `-gc` on HotSpot:

| Column | Meaning | Unit |
| --- | --- | --- |
| `S0C`, `S1C`; `S0U`, `S1U` | Capacity and used of the two survivor spaces | KB |
| `EC`, `EU` | Eden capacity and used | KB |
| `OC`, `OU` | Old capacity and used | KB |
| `MC`, `MU` | Metaspace committed and used | KB; **off-heap** |
| `CCSC`, `CCSU` | Compressed class space committed and used | KB; **off-heap** |
| `YGC`, `YGCT` | Young GC count and total time | Count; seconds |
| `FGC`, `FGCT` | Full GC count and total time per tool counters | Count; seconds |
| `GCT` | Total GC time reported by the tool | Seconds |

In `-gcutil`, columns `S0`, `S1`, `E`, `O`, `M`, and `CCS` are **utilization % of each individual region**; the GC counter columns keep their cumulative meanings. Some versions/collectors include or omit certain columns; **trust the header printed by the actual command**. `jstat` is documented by the JDK as an experimental/unsupported tool whose format may change, so **do not build long-term monitoring pipelines dependent on parsing a fixed text table**.

### Reading changes, not just a single row

Illustrative example of **two hypothetical samples** (these numbers are not guaranteed program stdout):

| Point | `E` | `O` | `YGC` | `YGCT` | `FGC` |
| --- | ---: | ---: | ---: | ---: | ---: |
| t0 | 92% | 38% | 7 | 0.120 s | 0 |
| t0 + 5 s | 14% | 41% | 9 | 0.145 s | 0 |

In 5 seconds there is `ΔYGC = 2` and `ΔYGCT = 0.025 s`; Eden dropped sharply while Old edged up slightly. This pattern aligns with allocation + young GC + some objects being retained/promoted. From two rows alone you **cannot** prove that all growth in Old came from promotion, nor prove a leak. `FGC = 0` does not mean "zero GC activity": other collections and concurrent work can run depending on the collector.

## 8. Workflow to cross-check all three sources in one measurement round

### Step 1 — lock identity and configuration

Record the PID, Java version, active GC, `-Xms/-Xmx`, and sampling start time. Do not compare output from an exited PID with a new process that reused that PID.

### Step 2 — establish a baseline

Record `Heap used/committed/max` from MXBean; take one `GC.heap_info` snapshot; run `jstat -gc` and `-gcutil` in the same time window, e.g. 5–30 seconds. Save application timestamps with metrics; if timestamps drift significantly, capture samples closer together.

### Step 3 — normalize units and meanings

For `jstat -gc` output containing traditional generational columns, you can compute **estimates**:

```text
heap_used_KiB      ≈ S0U + S1U + EU + OU
heap_capacity_KiB  ≈ S0C + S1C + EC + OC
heap_used_MiB      ≈ heap_used_KiB / 1024
heap_capacity_MiB  ≈ heap_capacity_KiB / 1024
heap_used_percent  = 100 × MXBean.heap.used / MXBean.heap.committed
```

This is a cross-check for compatible layouts, **not a universal law for every collector**: G1 uses flexible regions; non-generational collectors do not split Eden/Survivor/Old traditionally; some metrics/capacities calculate differently. Never include `MC/MU/CCSC/CCSU` in `heap_used_KiB` because those are non-heap.

**Hypothetical arithmetic check example**: `EU=14336 KB`, `S0U=0 KB`, `S1U=2048 KB`, `OU=32768 KB` ⇒ total `49152 KB = 48 MiB`. If the corresponding total capacity is `98304 KB = 96 MiB`, committed utilization is about `50%`. An MXBean returning `heap.used≈48 MiB` and `committed≈96 MiB`, alongside `GC.heap_info` near that timestamp, represents *consistent* observations; do not demand exact byte equality.

### Step 4 — re-measure after one or more natural GC cycles

Observe changes in `EU`, `OU`, `YGC`, `FGC`, `YGCT`, `GCT`; also compare **post-GC baseline** against request traffic/workload. For example, `used` climbing under higher load and falling after collection differs markedly from `used`/Old rising across many cycles while workload stays steady.

### Step 5 — write a qualified conclusion

Good conclusion template: "On HotSpot 21/G1, this PID has roughly 96 MiB committed heap and ~48–51 MiB used across three closely spaced measurements; over 10 seconds YGC increased by 3, Eden dropped after young GCs, and Old stayed around 35–38 MiB; no evidence of a heap leak is visible from this short window." Be sure to cite collector, sampling window, load, and uncertainty.

## 9. Interpreting common combinations

| Combined observation | Reasonable interpretation | Next check |
| --- | --- | --- |
| `EU` climbs fast then drops, `YGC` rises, `heap.used` oscillates | Short-lived allocations reclaimed by GC; may be normal | Check GC time, throughput, pauses/latency; do not rush to raise heap. |
| `OU` and post-GC `used` rise across many cycles at steady load | Possible object retention, growing cache, or leak | Compare over a longer window against actual load and live set; if needed use GC logs/heap dumps via a dedicated workflow. |
| `heap.used` is low while `committed` stays high | JVM retains committed heap or is affected by `-Xms`/GC policy | Check `max`, `committed`, and GC configuration; do not equate committed with a leak. |
| `jstat` shows high `M`/`CCS`, stable heap | Class metadata/non-heap pressure, not directly Java heap objects | Inspect non-heap MXBeans and class loading; do not add metaspace to heap. |
| OS RSS is high while heap and metaspace are low | Likely native memory, direct buffers, stacks, mapped pages, or native libraries | Use OS tools and native diagnostics; the three sources here cannot pinpoint that culprit. |
| `FGC` rises and `FGCT` grows fast alongside bad latency | Full GC may be causing significant pressure or pauses | Cross-check GC logs, allocation rate, old occupancy, and latency targets. |
| `GC.heap_info` differs from MXBean by a few MiB while `jstat` fluctuates sharply | Measurements are not simultaneous; pools/units have distinct representations | Capture closer in time, convert to MiB, verify matching PID/GC, do not "fudge" numbers to force a match. |

**Note on leaks:** a single increase in `used` or one Full GC does not prove a leak. The meaningful signal is a sustained upward drift in the baseline after multiple collection cycles when workload/caches have stabilized. To prove which objects are retained, you need evidence from heap dumps, dominator/retained-size analysis, or specialized tools.

## 10. Mistakes to avoid

1. **Comparing `max` with `total` as the same quantity:** `max` is a limit; `total/committed` is capacity currently committed at measurement time.
2. **Reading `O = 80%` as "heap 80%":** `O` is only old space %; the heap has other regions.
3. **Adding metaspace into heap:** `MC/MU` and `CCS` are not Java heap object bytes.
4. **Forgetting unit conversions:** `jstat -gc` uses KB, MXBeans use bytes, and GC times mix seconds/milliseconds.
5. **Comparing three readings as an atomic snapshot:** the process continues allocating and running GC between commands.
6. **Treating `used` as live set:** before GC, `used` can include unreachable objects not yet reclaimed.
7. **Assuming every JVM has identical Eden/Old/G1 pools:** pool names and output depend on collector/JVM; summing spaces is only a conditional estimate.
8. **Inferring "FGC didn't increase so GC isn't running":** check `YGC` and collector-appropriate indicators.
9. **Forcing `System.gc()` or `jcmd ... GC.run` before measuring:** distorts natural state and can introduce pauses.
10. **Ignoring access permissions:** `jcmd` requires active attach support and proper permissions; some JVMs disable attach. `jstat` requires available performance instrumentation; differing users/containers/namespaces may block access. Minimal runtimes may not bundle `jcmd`/`jstat`.
11. **Taking only a single `jstat` line:** cannot reveal ΔGC or trends.
12. **Writing parsers dependent on `jstat` column positions:** tool docs warn the format may change across versions.

## 11. Self-verification practice exercise

Using the program in section 4, observe for at least 30–60 seconds in two terminals:

1. Record `PID`, Java version, `-Xms`/`-Xmx`, and active collector.
2. Capture `GC.heap_info` twice about 15 seconds apart; extract total heap figures and separate out metaspace.
3. Record 5–10 samples of `jstat -gc` and `jstat -gcutil`; compute `ΔYGC`, `ΔYGCT`, `ΔFGC`. Observe how `EU`/`OU` change.
4. Copy two snapshots of `Heap used/committed/max` and heap pool names/usage from MXBean stdout; convert `used` to MiB.
5. Compare nearby timestamps; explain differences by timing, units, collector, and objects held by `RETAINED`.
6. Write a 3–5 sentence qualified conclusion: **which** numbers agree, where they diverge, how `YGC/FGC` changed, and what evidence is still missing before claiming a "leak".

**Passing criteria:** accurately separate heap and non-heap; distinguish `used/committed/max`; compute and explain ΔGC; understand why the three sources align closely without matching identically; never conclude a leak from a single snapshot.

## 12. Official reference documentation

- [JDK 21 — `jcmd`, `GC.heap_info` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [JDK 21 — `jstat`, syntax, columns, and tool limitations](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstat.html).
- [Java 21 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html).
- [Java 21 — `MemoryPoolMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html).
- [Java 21 — `MemoryUsage`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html).

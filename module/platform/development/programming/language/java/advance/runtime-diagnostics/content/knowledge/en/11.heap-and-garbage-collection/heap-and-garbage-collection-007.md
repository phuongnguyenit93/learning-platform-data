# 11.7. Column limits and experimental format of jstat when automating

## 1. Problem and target outcomes

`jstat` is a JDK-bundled tool for observing statistics of a running HotSpot JVM, especially memory region utilization and garbage collection (GC) counters. When inspecting a slow process or signs of heap pressure, a few `jstat` commands often provide a very quick initial view. However, **`jstat` output is not a stable data contract for automated monitoring software**.

After this lesson, the learner can:

- Choose the right column groups of `-gc` and `-gcutil`, and understand percentages, KB, counts, and seconds.
- Explain why column positions, counts, formatting, and meanings must not be assumed fixed across environments.
- Identify the effects of `-t`, `-h`, collector, JDK version, sampling timing, and PID lifecycle.
- Design schema checks and error handling for an ad-hoc analysis tool, while choosing JMX/JFR/GC logs for long-term monitoring.

**Scope:** this lesson focuses on the reliability of metric columns and consuming `jstat` output. Selecting a GC, tuning the heap, and deep pause analysis require additional data.

## 2. Understanding the "experimental" status accurately

Oracle JDK documentation for the `jstat` command explicitly marks the tool as **experimental and unsupported** and warns against writing scripts that parse its output format because it may change in future releases. From this it follows that:

1. A command succeeding today **does not prove** that headers, column counts, decimal digits, or column order are an immutable API across all JDK releases.
2. Options and statistical capabilities may also change, be removed, or correspond differently when switching VMs/collectors.
3. Table output that looks "easy to parse" is meant for human observation; the fact that Google Sheets, shell, Java, or Python can read the table does not turn it into an official protocol.
4. `experimental` **does not mean** every number is wrong. It describes the level of compatibility and support guarantees. It can be used for manual diagnostics, but you cannot promise that a production metrics exporter will not break after an upgrade.

`jstat` reads statistics published by an instrumented HotSpot JVM. It does not replace detailed GC event traces, heap dumps, or application latency measurements. A single sampled snapshot can miss a pause that occurred between two samples.

## 3. Basic observation commands

~~~bash
# See which modes the installed jstat binary actually supports
jstat -options

# Example PID 21891: 5 samples, roughly 1 second apart, with uptime and repeated header
jstat -gcutil -t -h3 21891 1000 5

# Heap region capacities/usage; compare with percentage metrics
jstat -gc 21891 1000 5

# GC cause information if the VM supports this option
jstat -gccause 21891 1000 5
~~~

The typical syntax is `jstat <statOption> [-t] [-hN] <vmid> [interval [count]]`. `interval` defaults to milliseconds; you can write `1s` or `1000ms` explicitly. When `interval` is specified without `count`, the command keeps sampling until stopped or the target process exits; automated jobs should set a finite sample count/timeout.

- `vmid` is usually the local JVM PID, though not every environment guarantees `vmid` matches the OS PID; processes in containers/namespaces can cause confusion. Confirm the exact JVM.
- `-t` prepends a `Timestamp` column: seconds since the target JVM started, **not** Unix epoch or wall-clock time.
- `-h3` repeats the header row every three samples; do not treat the second header row as numeric data.
- Actual sampling times experience jitter when the JVM or OS is busy, and are not guaranteed to be spaced at exactly 1.000 second.
- `-gcutil` is often handy for quick ratios; `-gc` shows capacities reported in KB. Do not infer an absolute quantity from a percentage without knowing the denominator and measurement time.

The output is plain text with whitespace-separated fields padded into columns for human readability. "Column 8" carries no durable meaning on its own.

## 4. Column meanings: names matter more than positions

The groups below describe naming in the Oracle JDK 25 documentation; **any real running system must verify headers and documentation for its exact JDK/VM**. The table is a reading glossary, not a list of columns guaranteed to exist in every environment.

| Common columns | Mode | Content and unit | Usage limitations |
| --- | --- | --- | --- |
| `S0`, `S1` | `-gcutil` | Utilization of the two Survivor spaces, % of current capacity | Does not give absolute bytes; memory region representation depends on collector |
| `E` | `-gcutil` | Eden utilization, % of current capacity | Climbs/drops rapidly with allocation and GC; one high sample does not prove a leak |
| `O` | `-gcutil` | Old space utilization, % of current capacity | Not synonymous with % of total heap; capacity can change |
| `M` | `-gcutil` | Metaspace utilization, % of current capacity | Metaspace belongs to native memory; do not treat it like Eden/Old |
| `CCS` | `-gcutil` | Compressed Class Space utilization, % | Do not expect every collector/JVM to emit the same field |
| `S0C/S1C`, `S0U/S1U` | `-gc` | Capacity/used of Survivor spaces, KB | `C` and `U` are two distinct quantities |
| `EC/EU`, `OC/OU` | `-gc` | Capacity/used of Eden and Old, KB | Values reported per the JVM's memory-region model |
| `MC/MU`, `CCSC/CCSU` | `-gc` | Committed/used Metaspace and Compressed Class Space, KB | "Committed" is not synonymous with "maximum" |
| `YGC`, `FGC` | `-gc`, `-gcutil` | Young GC and Full GC event counters | Cumulative counts; do not infer all events or pauses from these two columns alone |
| `YGCT`, `FGCT`, `GCT` | `-gc`, `-gcutil` | Reported cumulative GC time, **seconds** | Not directly p95/p99 latency, and not GC event count |
| `LGCC`, `GCC` | `-gccause` | Cause of last/current GC (when available) | Text fields; values can contain spaces, so do not parse as numbers |

For example, `OU = 300000` in `-gc` is interpreted in **KB**, whereas `O = 75.00` in `-gcutil` means **75% of current Old capacity**. You cannot treat `75.00` as 75 MB. When observing the same instant and the same reported region, you can roughly cross-check `OU / OC × 100`; do not treat this formula as valid when capacity is 0, metrics are incompatible, or samples were taken at different times.

Note that column names do not automatically express the semantics of every collector. Collectors with concurrent phases or different heap models may cause young/full/old classifications to diverge from what you expect from a traditional generational collector. `YGC/FGC/GCT` reflect instrumented counters, not a standardized event record across all collectors. When changing collectors, cross-check GC logs/JFR and re-verify your interpretation.

### Three number types that must not be mixed

- **Point-in-time gauges:** `E`, `O`, `EU`, `OU`, `EC`, `OC`. Can rise, fall, or change denominator after GC/resizing.
- **Cumulative counters:** `YGC`, `FGC`. Take the difference between two timestamps within **the same JVM lifetime**; never sum snapshot values directly into "GCs per minute".
- **Cumulative time:** `YGCT`, `FGCT`, `GCT`. Unit is seconds; the difference between two samples reflects the increase in the published time counter, does not show pause percentiles, and does not claim equality with total stop-the-world time.

## 5. Assumptions that easily break automation

| Wrong assumption | Example consequence | Control measure |
| --- | --- | --- |
| Column N is always `YGC` | Enabling `-t` shifts every index by one position | Look up by header name in every sampling session |
| Header appears only once | `-h3` feeds the literal string `YGC` into numeric parsing | Detect and skip/verify repeated headers |
| Every JDK has identical columns | Added/removed or renamed fields cause metric mislabeling | Record version, fingerprint header; fail closed on mismatch |
| Every cell is a finite number | Blank/N/A/`NaN` gets coerced to 0 by mistake | Check type and valid range; mark missing data explicitly |
| Multiple spaces mean multiple empty columns | A parser splitting on a single space shifts tokens | Split numeric columns on consecutive whitespace, verify exact field count |
| Every option outputs pure numbers | `-gccause` has text causes containing spaces | Parse per option schema; never parse `-gccause` like `-gcutil` |
| Timestamp is system wall-clock time | Dashboard plots uptime as an epoch in the wrong year | Use a separate wall-clock from the collector; Timestamp is for uptime correlation |
| Counters always increase between script runs | PID was reused or JVM restarted | Attach process identity + start time; reject negative deltas/resets |
| A 1000 ms interval is always exact | Computing rate from nominal interval is inaccurate | Use actual elapsed time or uptime delta when appropriate |
| `GCT` is total STW pause latency | Latency alerts are over-interpreted | Verify with GC logs/JFR and application latency measurements |
| Missing samples or exit code 0 means "normal GC" | Dashboards hide attach failures, timeouts, or permission errors | Distinguish missing-data state from numeric 0 |

In particular, never write parsers like `awk '{print $8}'` or `split(" ")[7]` and label the result `jvm_gc_events_total`. That only happens to work for **one** specific header layout. For long-lived metric emission, silent mislabeling is more dangerous than an explicit run failure.

## 6. Analyzing two samples without over-inferring

The snippet below **is illustrative data**, not mandatory output across all JDKs:

~~~text
Timestamp S0    S1    E     O     M     CCS   YGC YGCT  FGC FGCT  GCT
10.0      0.00  50.00 80.00 55.00 90.00 70.00 10  0.400 0   0.000 0.400
20.0      0.00  30.00 10.00 56.00 90.00 70.00 12  0.520 0   0.000 0.520
~~~

Between uptime 10 s and 20 s:

1. `ΔYGC = 12 - 10 = 2`: the young GC counter increased by two events.
2. `ΔYGCT = 0.520 - 0.400 = 0.120 s`: the young GC time counter increased by 120 ms.
3. `ΔGCT = 0.120 s` and `Δuptime = 10 s`: the counter-based descriptive ratio is `0.120/10 × 100 = 1.2%` for **this illustrative window**.
4. `E` dropped from 80% to 10% and `O` rose from 55% to 56%; these changes are consistent with allocation/collection activity, yet **insufficient** to prove which specific objects were promoted, a leak, or the maximum pause duration.

To evaluate service health, compare GC frequency, pause distributions in GC logs/JFR, throughput, and actual latency. The ratio of the GC time counter to uptime is only a preliminary signal; do not convert it directly into CPU percentage, total stop-the-world time, or latency SLAs.

## 7. Java 17+ example: a header-driven parser for test fixtures

This is **an exercise in processing saved snapshots** to demonstrate schema validation and rejecting malformed data; **it is not a recommendation to build a production exporter by scraping `jstat`**. The program does not attach to a JVM, so it runs on any machine with JDK 17+. It checks repeated headers, field counts, required columns, finite numbers, and counter resets. The simulated numbers are intentionally fixed so stdout is deterministic.

Save to `JstatHeaderDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class JstatHeaderDemo {
    record Sample(double uptime, long ygc, double ygct,
                  long fgc, double fgct, double gct) {}

    static double decimal(String[] data, Map<String, Integer> columns, String name) {
        double value = Double.parseDouble(data[columns.get(name)]);
        if (!Double.isFinite(value) || value < 0) {
            throw new IllegalArgumentException("Invalid " + name);
        }
        return value;
    }

    static long integer(String[] data, Map<String, Integer> columns, String name) {
        long value = Long.parseLong(data[columns.get(name)]);
        if (value < 0) {
            throw new IllegalArgumentException("Invalid " + name);
        }
        return value;
    }

    static List<Sample> parse(String output) {
        String[] signature = null;
        Map<String, Integer> columns = null;
        List<Sample> samples = new ArrayList<>();

        for (String line : output.lines().toList()) {
            String trimmed = line.trim();
            if (trimmed.isEmpty()) continue;
            String[] fields = trimmed.split("\\s+");

            if (fields[0].equals("Timestamp")) {
                if (signature != null && !Arrays.equals(signature, fields)) {
                    throw new IllegalArgumentException("Header changed");
                }
                signature = fields;
                columns = new HashMap<>();
                for (int i = 0; i < fields.length; i++) {
                    if (columns.put(fields[i], i) != null) {
                        throw new IllegalArgumentException("Duplicate column");
                    }
                }
                for (String required : List.of(
                        "Timestamp", "YGC", "YGCT", "FGC", "FGCT", "GCT")) {
                    if (!columns.containsKey(required)) {
                        throw new IllegalArgumentException("Missing " + required);
                    }
                }
                continue; // Repeated header is not a snapshot.
            }

            if (columns == null || fields.length != signature.length) {
                throw new IllegalArgumentException("Missing header or bad row width");
            }
            samples.add(new Sample(
                decimal(fields, columns, "Timestamp"),
                integer(fields, columns, "YGC"),
                decimal(fields, columns, "YGCT"),
                integer(fields, columns, "FGC"),
                decimal(fields, columns, "FGCT"),
                decimal(fields, columns, "GCT")
            ));
        }
        if (samples.size() < 2) {
            throw new IllegalArgumentException("Need at least two samples");
        }
        return samples;
    }

    public static void main(String[] args) {
        String fixture = """
            Timestamp S0 S1 E O M CCS YGC YGCT FGC FGCT GCT
            10.0 0.00 50.00 80.00 55.00 90.00 70.00 10 0.400 0 0.000 0.400
            Timestamp S0 S1 E O M CCS YGC YGCT FGC FGCT GCT
            20.0 0.00 30.00 10.00 56.00 90.00 70.00 12 0.520 0 0.000 0.520
            """;

        List<Sample> samples = parse(fixture);
        Sample first = samples.get(0);
        Sample last = samples.get(samples.size() - 1);

        if (last.uptime <= first.uptime || last.ygc < first.ygc
                || last.ygct < first.ygct || last.fgc < first.fgc
                || last.fgct < first.fgct || last.gct < first.gct) {
            throw new IllegalStateException("Restart, reset or invalid time window");
        }
        System.out.printf(Locale.ROOT,
            "dYGC=%d, dYGCT=%.3f s, dGCT=%.3f s, dt=%.1f s%n",
            last.ygc - first.ygc, last.ygct - first.ygct,
            last.gct - first.gct, last.uptime - first.uptime);
    }
}
~~~

~~~bash
javac JstatHeaderDemo.java
java JstatHeaderDemo
~~~

Stdout of the fixture above:

~~~text
dYGC=2, dYGCT=0.120 s, dGCT=0.120 s, dt=10.0 s
~~~

**Key points in the code:** `columns.get(name)` looks up positions by header; the code uses no fixed indices. Repeated headers must match the initial header. Data that violates the session contract throws an exception instead of silently changing metric semantics. The program only understands the numeric fields of `-gcutil -t`, not `-gccause` text. If output from an actual JDK version has a different header, treat it as a schema change and re-validate before use.

The demo program also **does not verify process identity, same JVM lifetime, wall-clock time, or connectivity to the target**: those must be handled at the collection layer. Identical headers still do not guarantee semantic compatibility across HotSpot versions.

## 8. If temporary collection from jstat is unavoidable

Only do this in an environment with pinned JDK/VM/collector versions and accepted maintenance upon upgrades, such as a diagnostic script run during incident response. Minimum contract:

1. **Identify the source:** record `vmid/PID`, JVM start time, target JVM vendor/version, collector/flags when available, `jstat` binary version, exact command, and system timestamp when captured. Never merge reused PIDs.
2. **Prevent unbounded runs:** use `count`, subprocess timeouts, stdout/stderr byte caps, and exit code checks. If attaching fails due to user permissions, containers, an exited VM, or inaccessible perf counters, return an "unavailable" state.
3. **Validate structure:** retain raw headers, build a column-name map, verify required fields appear exactly once, and match token counts. If the schema changes, raise a contextual error and store raw data for inspection.
4. **Validate values:** accept only finite numbers within reasonable bounds; never coerce empty cells, parse errors, missing fields, or `NaN` to 0. Interpret percentages according to the collector's memory-region model before setting thresholds.
5. **Compute lifecycle-safe deltas:** confirm the JVM has not restarted, uptime increased, and counters did not decrease; separate gauges and counters; label units, time window, and sample count; never take differences across two distinct JVMs.
6. **Guard upgrades:** re-test against every actual JDK/collector in production and a fixture suite covering repeated headers, added/removed columns, missing values, timeouts, and restarts; never auto-"fix" by shifting indices.
7. **Monitor collection quality:** track failures/timeouts/schema mismatches; absent data must be surfaced explicitly, never filled with 0 or held stale indefinitely.

You can run `jstat -options` to discover options available in the active binary; that is **not** a machine-readable column schema. Test the command against the exact JVM in staging before using it in response runbooks. When collector configuration changes, re-evaluate metric semantics as well as parser syntax.

## 9. Alternative tools by need

| Need | Preferred alternative | Why it fits better than parsing jstat |
| --- | --- | --- |
| Quick diagnosis in a terminal session | `jstat`, paired with `jcmd <pid> GC.heap_info` | Fast, manual, allows cross-checking multiple views; avoids long-term schema commitments |
| Periodic metrics, dashboards, and alerts | JMX `MemoryMXBean`, `MemoryPoolMXBean`, `GarbageCollectorMXBean` via a suitable exporter | Typed management interface; still requires understanding the collector and access permissions |
| Exact timeline and duration of each GC/pause | Unified GC logging `-Xlog:gc*` or Java Flight Recorder (JFR) | Carries event context and timing; analyze with tools matching the JDK |
| Investigating abnormal heap or suspected leak | `jcmd` for heap info/histograms; heap dump after assessing impact | Reveals deeper object/heap structure; some commands can consume substantial resources |
| Evaluating service experience | p95/p99 latency, error rate, throughput, CPU, memory + GC | Captures real user symptoms; GC is only one source of evidence |

Example of gathering inspection details via `jcmd` (only when permitted to access the process):

~~~bash
jcmd 21891 VM.version
jcmd 21891 VM.flags
jcmd 21891 GC.heap_info
~~~

When using GC logs, an example configuration for modern HotSpot is:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Logging syntax and tag sets should also be checked against the deployed JDK release. Do not trigger expensive operations like heap dumps or class histograms in production merely to compensate for missing columns in `jstat`.

## 10. Self-check checklist and exercises

Before trusting any chart built from `jstat`, be able to answer: which JVM is being observed; which JDK and GC; whether the columns exist in actual output; what the units are; which samples are missing; whether a restart occurred; what actual sampling intervals were; how version changes are detected; and which GC logs/JFR or latency metrics corroborate it.

**Exercise 1.** Suppose a parser hard-codes index 7 to read `YGC`. After adding `-t`, explain why that number can shift to another column; modify the parser to look up `YGC` by header name.

**Exercise 2.** In the Java fixture, replace one repeated header with a header missing `GCT` and rerun. Expected result: the program rejects the input with `Header changed` instead of emitting metrics. Next, change a numeric row's `YGCT` field to `NaN`: expected result is `Invalid YGCT`.

**Exercise 3.** After a deployment, `YGC` drops from 150 to 3. Why must you not compute `ΔYGC = -147` and plot it? Check process start time/uptime and exclude comparison windows spanning a restart.

**Exercise 4.** `O` climbs steadily while service latency is normal. Is that enough to conclude a memory leak? No: you need post-collection heap/GC history, retention evidence, GC logs/JFR, and application-level evidence.

**Key message:** `jstat` is a useful diagnostic tool for human readers, but its experimental format is not a stable schema for automation. Respect column names, units, JVM lifecycle, collector behavior, and missing-data states; use dedicated telemetry sources when durable metrics are needed.

## Reference documentation

- Oracle Java SE 25, [The jstat Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jstat.html) — syntax, data columns, `-t`/`-h` examples, and experimental warning.
- Oracle Java SE 25, [Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html) — guidance on using `jcmd` and JFR for JVM investigation.
- Oracle Java SE 25, [The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html) — configuring Unified Logging via `-Xlog`.

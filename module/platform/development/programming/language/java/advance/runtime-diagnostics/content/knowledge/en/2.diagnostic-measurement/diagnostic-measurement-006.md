# 2.6 Aligning Timestamps, Timezones, and Uptimes Across Multiple Data Sources

When investigating a JVM incident, data usually arrives from many places: application logs, GC logs, Java Flight Recorder (JFR), thread dumps, OS metrics, Kubernetes, Prometheus, and distributed traces. These sources may all record **the same real event** yet express time in **UTC, local time, epoch, uptime since JVM start, uptime since OS boot, or the time the monitoring system ingested the data**. If un-normalized numbers are stitched together directly, timelines can shift by hours, invert causal order, or invent "negative latency".

This lesson aims to build **a trustworthy diagnostic timeline**: understand the semantics of each clock, normalize points in time to UTC when justified, convert uptimes using reference anchors belonging to the exact process or boot, record uncertainty, and preserve raw data for auditing.

## 1. Two Different Questions: "When?" and "How Long?"

An event has at least two temporal aspects:

- **Absolute time (wall-clock time):** "GC started at 08:14:05.400 UTC". Used to place events from multiple machines onto the same timeline.
- **Elapsed duration:** "A task ran for 150 ms". Used to measure latency, pause length, or timeouts; prefer a monotonic elapsed clock within the same environment.

These quantities do not convert automatically into one another:

- `2026-10-29T08:14:05.400Z` is a UTC instant with global meaning **up to the accuracy of the source clock**.
- `905400 ms` since JVM start **means nothing on a global timeline** until you know which JVM it belongs to and its JVM start anchor.
- `8045400 ms` since OS boot is completely different from JVM uptime, even though both are in milliseconds.
- `System.nanoTime()` returns values from an arbitrary origin; only **subtracting two values within the same JVM** produces a meaningful interval.
- Collector ingest time is usually **later** than when the log was emitted; that is a different timestamp field.

A diagnostic question such as "Did GC happen while p99 spiked?" requires **the start time and duration of GC**, the measured p99 window, clock sources, clock skew across nodes, and workload scope. Seeing two log lines close together is not enough to conclude causality.

## 2. Identify the Exact Clock Type

| Time Type | Meaning and Appearance | Can Be Merged Directly Across Sources? | Limitations |
| --- | --- | --- | --- |
| **UTC instant** | `2026-10-29T08:14:05.250Z`; Java `Instant`, ISO 8601 with `Z` | Yes, after assessing skew and emission time | Host clock can be wrong or adjusted |
| **Wall-clock with offset** | `2026-10-29T15:14:05.250+07:00` | Yes: convert to the same `Instant` | Offset locates position on timeline; does not tell clock accuracy |
| **Local time without zone/offset** | `2026-10-29 15:14:05` | **No**; requires zone metadata and DST rules on that date | Can be ambiguous or non-existent across DST transitions |
| **Epoch timestamp** | Seconds/ms/µs/ns since `1970-01-01T00:00:00Z` | Yes if **unit** and semantics are known | Confusing seconds and milliseconds shifts dates by millennia; ns in floats loses precision |
| **JVM uptime** | `905400ms` or `905.400s` since JVM started | Only after identifying exact JVM instance and anchor | Resets on JVM restart; start time may be approximate |
| **OS boot uptime / monotonic** | `[8045.400000]` in journal as time since boot | Only after identifying exact host/boot ID and anchor | Resets on reboot; depends on clock and suspend/virtualization behavior |
| **High-resolution elapsed clock** | `System.nanoTime()` | Only subtract differences within **the same JVM** | Not epoch nanoseconds; never use raw integers to align multiple JVMs |
| **Event duration** | JFR `duration=120 ms`, span duration, GC pause 18 ms | Compare lengths after verifying units | Does not tell when the event started on its own |
| **Observed/ingest/scrape time** | Collector received log at 08:14:06; Prometheus sample at scrape | Yes if analyzing ingestion/scraping | Does not automatically equal when the business event happened |

**Distinguish clearly:** "right timezone" and "accurate clock" are two independent issues. Converting `+07:00` to `Z` fixes *how* the same instant is written; it does not fix a node whose clock runs 200 ms fast relative to reference time.

### 2.1. Wall Clock and Monotonic Clock in Java

- `Instant.now()` and `System.currentTimeMillis()` rely on system wall time, used for timestamps exchanged across processes. They are affected by clock sync, manual adjustments, and clock resolution.
- `System.nanoTime()` is for measuring elapsed time; its origin is arbitrary and unrelated to UTC. Compute `endNs - startNs` within the same JVM for durations; never store `nanoTime` as UNIX epoch.
- `ManagementFactory.getRuntimeMXBean().getStartTime()` returns **approximate JVM startup time** in epoch milliseconds; `getUptime()` returns JVM uptime in milliseconds.
- `ZoneId.systemDefault()` only controls local date/time formatting per process configuration; it **does not change** the host's UTC clock.

In diagnostics, record both `event_time_utc` and `elapsed_duration_ms` when both are useful. A process can still record accurate durations using a monotonic clock even if wall clock is stepped, whereas using a skewed wall clock to order events across two machines can still mislead.

## 3. Timezone Normalization: One Instant, Many Formats

The same point in time can be written as:

| Source Representation | Normalized UTC | Notes |
| --- | --- | --- |
| `2026-10-29T15:14:05.250+07:00` | `2026-10-29T08:14:05.250Z` | Subtract offset +07:00 **once** |
| `2026-10-29T08:14:05.250Z` | Unchanged | `Z` corresponds to UTC+00:00 |
| `1793261645.25` UNIX seconds | `2026-10-29T08:14:05.250Z` | Seconds with fractional part |
| `1793261645250` UNIX milliseconds | `2026-10-29T08:14:05.250Z` | Integer milliseconds |

**Never** read `15:14+07:00` as `15:14Z` and then add/subtract 7 hours again. The offset is already applied when converting `OffsetDateTime` to `Instant`.

### 3.1. Offset Differs from ZoneId

- `+07:00` is a **fixed offset** relative to UTC at a point in time.
- `Asia/Ho_Chi_Minh` is a **zone ID** with historical timezone rules.
- `America/New_York` is a zone with DST rules; the same local clock `01:30` on fall-back day can map to **two distinct instants**. In spring, certain local wall-clock intervals **do not exist**.

A string `2026-11-01 01:30:00` on a New York host cannot determine on its own whether it occurred before or after the DST fallback; you need offset, zone, system metadata, and context. `LocalDateTime` cannot represent a unique instant without a zone/offset. Never attach the **analyzing machine's** default zone to logs pulled from another host.

If logs have only `dd/MM/yyyy HH:mm:ss` with no offset, mark status **unresolved** until verifying the source's timezone config *at the time the log was generated*. If forced to assume a zone to proceed with investigation, explicitly record the assumption and keep the raw log.

### 3.2. Precision Differs from Accuracy

A timestamp with 9 digits after the decimal point does not mean the clock is accurate to the nanosecond. Distinguish:

- **Precision / resolution:** granularity of the numeric field or sampling source (seconds, milliseconds, microseconds, nanoseconds).
- **Accuracy:** closeness to true reference time, affected by NTP/PTP, node skew, clock drift, and delayed timestamping.
- **Uncertainty:** estimated error margin, e.g., `±20 ms`.
- **Event time vs. observed time:** the application emits the event first; the collector may receive it later due to queues, buffers, or network.

Do not round down to whole seconds when correlating a 20 ms GC pause with request timeouts; likewise, do not pad `.000000` digits implying higher measurement accuracy than actually exists.

### 3.3. Avoid Confusing Epoch Units

The value `1793261645250` in the example is **milliseconds**; dividing by 1,000 gives `1793261645.25` seconds. Do not guess units solely from digit count, because historical dates, negative timestamps, decimals, and custom formats break that heuristic. Include explicit fields or metadata like `timestamp_unit=ms`, `epoch=unix`.

In Java, use `Instant.ofEpochMilli(epochMs)` for ms; for seconds and nanos, use `Instant.ofEpochSecond(seconds, nanos)`. When exporting to JavaScript, JSON, or analysis tables, avoid passing 19-digit epoch nanoseconds through IEEE-754 double floats because nanosecond precision is lost; prefer strings or true 64-bit integer types where supported.

## 4. Uptimes Must Be Bound to the **Exact Time Origin**

There are at least three distinct origins in a system:

1. **Node/OS boot:** Linux monotonic/boottime per boot instance; systemd journal tracks boot IDs and can display `short-monotonic`.
2. **JVM launch:** Java unified logging `uptime`/`uptimemillis` and RuntimeMXBean uptime count from JVM startup.
3. **Task/request/recording start:** `System.nanoTime()` measures elapsed from an arbitrary origin; JFR recordings have their own start/end times.

**Each origin must carry its identity**. PIDs can be reused after restarts; pod names can persist across container restarts; boot uptime resets on reboot. Carry node ID, boot ID, container ID, JVM start instant, PID, deployment version, and recording ID as needed.

### 4.1. Conditional Conversion from Uptime → UTC

If you have a **simultaneous anchor pair** for the same clock:

- `anchor_utc` is the normalized absolute timestamp.
- `anchor_uptime_ms` is the corresponding uptime of **that exact process/JVM**.
- The event has `event_uptime_ms`.

When the clock runs steadily over the observed interval:

```text
event_utc_estimate = anchor_utc
                   + (event_uptime_ms - anchor_uptime_ms)

Example: anchor_utc=08:14:05.000Z, JVM uptime at anchor=905000ms
         event_uptime=905400ms
         => estimated event_utc = 08:14:05.400Z
```

This is an **anchor-based estimate**, not an infallible law: capturing the anchor has lag, and clocks can be stepped or drift. If multiple anchors exist across time, check residuals to detect clock steps/slews. For critical data, attach `uncertainty_ms` rather than treating calculated timestamps as absolute exact truth.

A simpler approach when GC logs include **both `utctime` and `uptimemillis` on the same line** is to use that line's UTC timestamp and uptime to cross-verify. This is why enabling both decorators together when configuring diagnostic logging upfront pays off.

### 4.2. Never Substitute OS Uptime for JVM Uptime

Suppose in a **synthetic example**:

- OS boot at `2026-10-29T06:00:00Z`.
- JVM start at `2026-10-29T07:59:00Z`.
- A GC occurs at `2026-10-29T08:14:05.400Z`.

At the GC instant, JVM uptime is **905.400 s**, whereas OS uptime is **8,045.400 s** (2 hours, 14 minutes, 5.400 seconds). Adding `905.400 s` to OS boot places the GC nearly **1 hour 59 minutes** too early. Every conversion must use the matching clock origin and exact instance.

With containers, do not assume pod creation time equals JVM start time: containers can restart; init containers and app containers start at different times; PID namespaces can also make the PID seen from the host differ from the PID inside the container. Some environments also have time namespaces or clock shifts from VM suspend; check actual runtime context before inferring origins.

## 5. Each Diagnostic Source Has Its Own Time Semantics

### 5.1. Application Logs

Prefer a timestamp field with an explicit offset, such as `2026-10-29T08:14:05.250Z`; use `Instant` or a standard ISO 8601 formatter. If the app logs local time, know the process's actual zone/offset when the log was emitted. Include request/trace ID, service, instance/container, PID, or process start ID when helpful.

Distinguish `event_time` (when code emitted the event) and `observed_time`/`ingest_time` (when the agent or collector received it). In async pipelines, lines can arrive late at dashboards; sorting by ingest time can invert the order of two events.

### 5.2. HotSpot JDK 17+ GC Logs

JVM unified logging supports these main decorators:

| `-Xlog` Decorator | Meaning | How to Align |
| --- | --- | --- |
| `utctime` | UTC timestamp on log line | Use as instant if host clock is trustworthy |
| `time` | Timestamp in environment's display timezone | Parse offset too; avoid assuming UTC |
| `uptime` | Seconds since JVM start | Align only within the same JVM |
| `uptimemillis` | Milliseconds since JVM start | Convenient to map to instant via anchor |
| `timemillis` | Wall-clock epoch milliseconds | Verify unit and timestamp semantics |
| `timenanos` | From `System.nanoTime()`, **not epoch ns** | Never treat as UNIX epoch |
| `pid`, `tid`, `tags`, `level` | Metadata tying log line to process/event type | Prevents mixing sources and warnings |

Example startup configuration; paths and file sizes are examples, adjust per environment:

```bash
java '-Xlog:gc*,safepoint:file=gc.log:utctime,uptimemillis,pid,level,tags:filecount=5,filesize=20M' -jar app.jar
```

This stamps both **UTC** and **JVM uptime** onto GC/safepoint logs. Check `java -Xlog:help` on your exact JDK version to confirm decorators, tags, and file write permissions. Do not alter production logging solely for an educational example; weigh overhead and change procedures.

An illustrative line can be read as "around UTC 08:14:05.400, JVM instance X reached uptime 905.400 s and a GC event occurred". Event labels, durations, and pause phases must be read from **the actual GC message**; never infer pause length from a single line's timestamp alone.

### 5.3. Java Flight Recorder (JFR)

JFR records events with **start time, duration**, and event-specific fields (GC, allocation, locks, I/O, etc.). Recording files have start/stop bounds. JFR viewers may display times in the analyst's local timezone; record the active display zone and convert to `Instant` before merging with other logs.

A non-instant JFR event is **an interval [start, end]**; `end = start + duration`, not collapsed to a single point. If an event starts at `08:14:05.300Z` with `duration = 120 ms`, it ends at `08:14:05.420Z`. A GC at `08:14:05.400Z` falls inside that interval, yet temporal overlap alone does not prove GC caused all the latency. Inspect event type, thread, correlation IDs, phases, and quantitative metrics.

Example commands to inspect summary metadata and one event type in a collected file:

```bash
jfr summary incident.jfr
jfr print --events jdk.GarbageCollection incident.jfr
```

Interpret output according to JDK version and viewer; when millisecond comparison is needed, export absolute times with explicit zones, record recording metadata, and check precision limits.

### 5.4. Thread Dumps and Diagnostic Command Snapshots

A thread dump is **a snapshot taken while the command executes**, which can take non-zero time to capture. Do not assume a header timestamp at the top of the file represents the exact instant of every thread state inside the file. If a dump lacks a trustworthy timestamp, bracket it between two UTC readings on the same host:

```bash
# Linux example, with the exact JVM's hypothetical PID.
date -u '+%Y-%m-%dT%H:%M:%S.%NZ'
jcmd 12345 Thread.print -l > thread-dump.txt
date -u '+%Y-%m-%dT%H:%M:%S.%NZ'
```

Now you know the **capture window** of the dump instead of inventing a false exact instant. Record PID, JVM start, host, timezone, and capture reason. With multiple dumps, note varying capture durations; do not confuse storage upload time with dump creation time.

### 5.5. Linux Kernel, systemd Journal, and OS Boot Time

- `journalctl -b -o short-iso-precise` shows journal entries for one boot with high-precision ISO timestamps.
- `journalctl -b -o short-monotonic` shows timestamps on that boot's monotonic clock.
- `journalctl --list-boots` helps identify boot instances across reboots.
- `/proc/uptime` shows OS uptime, **not how long the JVM has been running**.
- `dmesg` can print relative timestamps since boot; converting them to wall time via tool flags can be wrong if system wall clock was adjusted or the system suspended/resumed.

Illustrative read-only commands on a Linux machine running systemd:

```bash
journalctl --list-boots
journalctl -b -o short-iso-precise
journalctl -b -o short-monotonic
cat /proc/uptime
```

When mapping monotonic time to wall time, attach **boot ID** and a UTC anchor from that exact boot; two `[123.456]` lines from two different boots have no direct ordering relationship. If display timezone differs between host and terminal, convert only the **representation** to UTC without altering source time values.

### 5.6. Containers / Kubernetes

When reviewing a pod, distinguish the timestamps of:

- Pod created, scheduled, container started, JVM started, container restarted, liveness/readiness events, and log collection time.
- Kubelet/CRI logs carry their own timestamps; `kubectl logs --timestamps` prepends container stream timestamps. Runtime-assigned timestamps do not always match timestamps the application wrote inside its payload.
- `kubectl logs --previous` (when available) shows logs from the previous container instance after a restart; use container ID and restart count to separate two JVM lifetimes.
- Local time displayed inside a container can differ from host timezone even though they share the underlying wall clock; differing formatted strings are not necessarily clock skew.

An `OOMKilled` or restart event in Kubernetes Events is temporal evidence to correlate with the exact pod/worker instance, while keeping in mind events may be recorded or delivered to the control plane after actual impact.

### 5.7. Prometheus and Dashboard Metrics

Prometheus stores **sample timestamps** typically in epoch seconds; by default, timestamps reflect scrape/collection time or exporter-supplied timestamps when applicable. A CPU sample at `08:14:06` represents the value at scrape time; it does **not** mean all CPU usage in the window happened strictly at `08:14:06`.

- `timestamp(metric)` in PromQL returns epoch seconds of the selected sample.
- `rate(counter[5m])` represents an estimated rate over a **window**, not a point-in-time event.
- Dashboard histogram p95/p99 values are interval aggregates; know step, query window, label filters, and how the histogram was built.
- Grafana or the browser may render the same timestamp in the viewer's local timezone; verify dashboard timezone before reporting a "7-hour offset".

When aligning metrics with JFR/GC, place the **metric window** beside the **event's start–end interval**, rather than claiming points with different temporal semantics are strictly simultaneous.

### 5.8. Distributed Tracing and Cross-Node Telemetry

OpenTelemetry spans have start/end timestamps and trace/span IDs. Log records can distinguish **Timestamp** (when the event occurred) and **ObservedTimestamp** (when it was observed). When two services run on nodes with clock skew, a child span can appear to start before its parent or a request can look like it "arrived before it was sent" even though actual causality is valid.

To correlate, prioritize trace IDs, parent-child links, request/response IDs, protocol semantics, and durations measured within the same process, while checking clock sync across nodes. Do not manually "fix" charts by sliding a span by hundreds of milliseconds without measuring the real skew.

## 6. Clock Synchronization Across Hosts: NTP/PTP, Drift, Step, and Skew

Machines can all use UTC while **not agreeing on the exact current instant**:

- **Clock offset/skew:** difference between source clock and reference clock. E.g., host A runs 120 ms fast relative to reference time.
- **Clock drift:** offset changing gradually over time due to oscillators, VMs, temperature, or hardware.
- **Slew:** gradually adjusting clock speed to bring time back into alignment.
- **Step:** instantaneous clock jump, which can move wall-clock timestamps backward or forward.
- **Suspend, migration, reboot:** can create gaps, alter elapsed clock behavior, or reset uptimes.

NTP/chrony or PTP synchronize clocks; **never assume error = 0**. Collect time-sync status from **each node**, estimated offset, reference source, check timestamp, and uncertainty. Commands like `timedatectl` or `chronyc tracking` help inspect depending on OS and setup; do not assume running a command on your workstation proves every node in the cluster is tightly synced.

If defining `offset = source_clock - reference_clock`, then:

```text
corrected_utc = source_reported_utc - estimated_offset
```

A host running `+120 ms` fast: source timestamp `08:14:05.370Z` is estimated as `08:14:05.250Z`. Record the **sign of the offset** and uncertainty; flipping the sign doubles the error. If the offset was measured hours away from the incident or the clock stepped afterward, do not treat it as a reliable constant across the entire investigation.

Without sufficient clock-sync evidence, you may conclude "two phenomena happened close together in a window", yet **cannot** assert ordering at millisecond resolution.

## 7. Building a Timeline with an Auditable Process

### Step 1 — Choose the Question and Timeframe

Example: "Did a GC pause coincide with the 200 ms latency spike when checkout timed out?" Define the UTC incident window, service, and instance—not just a local calendar date.

### Step 2 — Collect Raw Data with Identity

For each source, preserve raw timestamps and original files; record:

- `source_type`, `source_file`, `host/node`, `pod/container`, `pid`, `jvm_start_utc`, `boot_id` if applicable.
- `raw_time`, `raw_unit`, `clock_domain` (wall UTC, wall local, JVM uptime, OS uptime, elapsed clock, ingest).
- `time_zone` or `offset`, DST info if source only has local timestamps.
- `event_time`, `observed_time`, `collection_window`, and artifact creation timestamp if they differ.
- `clock_offset_estimate`, `uncertainty`, parser version, conversion assumptions, and any missing data.
- `trace_id`, `request_id`, `thread_id`, or `gc_id` to link events sharing context.

This is **investigative metadata**—you do not need to cram every field into every application log line; it can live at the source/file/session level.

### Step 3 — Normalize to a Single UTC Axis

1. Timestamps with `Z` or explicit offset: parse to `Instant`.
2. Epoch seconds/ms/µs/ns: convert using the **declared** unit and sanity-check the date range.
3. Local timestamps missing zone: trace timezone config at emission time, resolve DST if applicable; if insufficient, mark "unresolved".
4. JVM uptime: find an anchor from the same JVM (ideally an event having both UTC and uptime), verify JVM start and restarts.
5. OS monotonic uptime: find an anchor from the same boot; verify boot ID.
6. Elapsed-only `nanoTime`: retain strictly for durations within the same JVM; never coerce raw numbers into instants.
7. Logs/snapshots captured over an interval: keep interval `[capture_start, capture_end]`.

Always store `original_timestamp` and `normalized_utc` in two separate fields; never overwrite raw data.

### Step 4 — Attach Uncertainty Before Ordering

Represent an event estimated at `t` with uncertainty `±e` as interval `[t-e, t+e]`. If two intervals overlap, chronological ordering between those two events is **uncertain** from clocks alone.

Example:

- Node A logs event at `08:14:05.250Z ±40 ms` → interval `[.210, .290]`.
- Node B logs event at `08:14:05.280Z ±40 ms` → interval `[.240, .320]`.

Even though B's timestamp is 30 ms greater than A's, the intervals overlap, so **you cannot claim A happened before B** at the stated confidence level. If trace propagation proves a send → receive relationship, that provides causal evidence independent of wall-clock ordering.

### Step 5 — Build a Timeline with Durations, Not Just Points

A timeline table should contain at least: `source`, `event`, `start_utc`, `end_utc` (if duration exists), `uncertainty`, `identity`, and `evidence`. Filter by the same request/instance, and align GC/JFR/trace intervals against metric increase windows. Aggregate metrics must show their **measurement window** (e.g., 08:14:00–08:15:00), rather than pretending to be a point at the midpoint.

### Step 6 — Cross-Check and Falsify

- Do `utctime` and `uptimemillis` in GC logs match the recorded JVM startup?
- Do JFR recordings, app logs, and JVM metrics span the same process/container restart?
- Is the clock offset smaller than the event gap you want to conclude about?
- Did any clock step, DST switch, reboot, or replay/ingestion delay happen in that interval?
- Do events from sampling/aggregation have enough resolution to assert ordering?
- Do trace IDs, GC IDs, and thread IDs actually match, or merely sit "near each other on a chart"?

If an assumption is refuted, update the mapping and rebuild the timeline; document the change clearly. Never silently add a few hours "to make it line up" or drop events that do not fit the hypothesis.

## 8. Example Aligning Five Sources for the Same Incident Window

This is **synthetic data to practice conversion**, not real output from an actual JVM:

- Host boot: `2026-10-29T06:00:00Z`.
- JVM instance `checkout-1` start: `2026-10-29T07:59:00Z`.
- Assume source clocks were verified with no significant offset; in practice always record uncertainty.

| Source | Raw Timestamp or Interval | Normalized UTC | What Is Known |
| --- | --- | --- | --- |
| Application log | `2026-10-29T15:14:05.250+07:00` | `08:14:05.250Z` | Checkout logged warning; request ID identified |
| JFR event | `start=08:14:05.300Z`, `duration=120 ms` | `[08:14:05.300Z, 08:14:05.420Z]` | A spanning event, potentially overlapping GC |
| OS journal | Boot uptime `8045.350 s` | `08:14:05.350Z` | Valid only for the exact boot anchored at `06:00Z` |
| GC unified log | JVM uptime `905400 ms`, `utctime=08:14:05.400Z` | `08:14:05.400Z` | GC belongs to exact JVM start `07:59Z` |
| Prometheus sample | Sample time `08:14:06.000Z` | `08:14:06.000Z` | Value at sample/scrape instant, **does not** pinpoint an individual event's time |

Numbers in the table are consistent: `07:59:00 + 905.400 s = 08:14:05.400Z`; `06:00:00 + 8045.350 s = 08:14:05.350Z`. The JFR interval spans across the GC instant; yet to say **GC caused the latency increase**, you need matching event type/duration, request traces with matching IDs, GC pause length, workload, and metrics ruling out other causes.

**Do not merge by row order or file arrival order.** Log aggregation can arrive delayed; files can reorder on rotation; JFR viewers can show local time. Sort by normalized time only **after** mapping and uncertainty are recorded.

## 9. Java 17+ Program Normalizing Timestamps and Verifying Uptime

The standalone example below uses fixed synthetic values for deterministic output. It converts a `+07:00` timestamp to UTC, computes the gap between the application event and GC, converts GC uptime from a known JVM start to UTC, and checks whether both readings agree.

Save with exact name **`TimelineAlign.java`**:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;

public class TimelineAlign {
    public static void main(String[] args) {
        Instant app = OffsetDateTime.parse(
                "2026-10-29T15:14:05.250+07:00").toInstant();

        Instant gc = Instant.parse("2026-10-29T08:14:05.400Z");
        Instant jvmStart = Instant.parse("2026-10-29T07:59:00Z");
        long gcUptimeMs = 905_400L;

        Instant gcFromUptime = jvmStart.plusMillis(gcUptimeMs);

        System.out.println("app_utc=" + app);
        System.out.println("gc_utc=" + gc);
        System.out.println("app_epoch_ms=" + app.toEpochMilli());
        System.out.println("gap_ms=" + Duration.between(app, gc).toMillis());
        System.out.println("gc_from_jvm_uptime=" + gcFromUptime);
        System.out.println("verified=" + gcFromUptime.equals(gc));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac TimelineAlign.java
java TimelineAlign
```

**Exact** stdout:

```text
app_utc=2026-10-29T08:14:05.250Z
gc_utc=2026-10-29T08:14:05.400Z
app_epoch_ms=1793261645250
gap_ms=150
gc_from_jvm_uptime=2026-10-29T08:14:05.400Z
verified=true
```

Explanation:

1. `OffsetDateTime.parse(...).toInstant()` applies the `+07:00` offset **once**, resulting in `08:14:05.250Z`.
2. `Duration.between(app, gc).toMillis()` gives the 150 ms gap from the app event to the GC instant. This is **the gap between two synthetic timestamps**, not the duration of the GC.
3. `Instant.plusMillis(905_400)` adds JVM uptime to a JVM start anchor **assumed known and belonging to the exact process**. In production, `getStartTime()` is approximate and clocks can drift; getting `true` in the example does not prove uptime conversion is always exact across every source.

### 9.1. Measuring Latency in Real Code Using an Elapsed Clock

For the latency of an internal operation, the proper way is usually:

```java
long startedNs = System.nanoTime();
try {
    // Perform the work to measure.
} finally {
    long elapsedNs = System.nanoTime() - startedNs;
    // Record elapsedNs alongside UTC timestamp and trace/request ID.
}
```

This is an **illustrative snippet inside a method**, not a standalone program. Never call `Instant.now()` twice and treat the difference as having monotonic-clock stability when the OS can step wall clock. Also never log raw `startedNs` as UNIX epoch nanoseconds. To correlate across systems, record `Instant.now()` at event time and `nanoTime` duration in two distinct fields.

### 9.2. Good Timestamp Format for Logs

An ideal JSON log record for distributed incidents might look like:

```json
{
  "event_time": "2026-10-29T08:14:05.250Z",
  "observed_time": "2026-10-29T08:14:05.310Z",
  "service": "checkout",
  "instance": "checkout-1",
  "jvm_start_time": "2026-10-29T07:59:00Z",
  "trace_id": "example-trace-42",
  "duration_ms": 150,
  "timestamp_unit": "iso8601-utc"
}
```

This data is illustrative only: `observed_time` may be added by a collector rather than the application. `duration_ms` is meaningful only when event docs specify start/end boundaries. `trace_id` supports joining requests without relying solely on timestamp proximity.

## 10. Common Mistakes That Corrupt Timelines

1. **Concatenating local strings directly as UTC:** `15:14+07:00` treated as `15:14Z`, off by exactly 7 hours.
2. **Converting timezones twice:** parsing the offset and then subtracting 7 hours again downstream.
3. **Confusing UTC format with synchronized clocks:** sources all printing `Z` can still be hundreds of milliseconds apart across nodes.
4. **Mixing JVM uptime with OS uptime:** same ms unit but different origins; creates errors of hours.
5. **Treating `nanoTime` as epoch nanoseconds:** meaningless in UTC; comparing across two JVMs is even worse.
6. **Confusing epoch seconds, milliseconds, microseconds, and nanoseconds:** dates land outside reasonable ranges or lose precision.
7. **Failing to separate restarts:** reused PIDs/pod names reset uptime to 0 while the pipeline adds it to the old anchor.
8. **Trusting collector time instead of event time:** network/buffering/replay creates false ordering.
9. **Comparing points while ignoring durations:** a GC pause, JFR event, or query window is an interval; overlapping intervals do not prove causality.
10. **Ignoring DST:** local times during seasonal transitions can be ambiguous or non-existent.
11. **Over-trusting decimal places:** printing nanoseconds does not mean clock/sync accuracy is nanosecond-grade.
12. **Discarding raw sources:** after normalizing incorrectly, there is no way to recover.
13. **Ignoring clock steps/reboots:** sudden wall jumps or monotonic resets break linear interpolation across intervals.
14. **Assuming spans always order by `startTime`:** cross-service clock skew can invert visual order; verify trace IDs and causal links.

## 11. Checklist Before Claiming Two Events Are Related

- [ ] Have you clarified the comparison goal: **point in time**, **duration**, **measurement window**, or **causal order**?
- [ ] Is every timestamp classified as UTC/offset/local/epoch/JVM uptime/boot uptime/elapsed/ingest?
- [ ] Are timezones/offsets and units recorded, with DST ambiguity handled if needed?
- [ ] Are uptimes bound to the exact JVM start/boot ID, PID/container instance, without crossing a restart?
- [ ] Are `System.nanoTime` values used strictly for durations within a single JVM?
- [ ] Were clock skew, sync status, steps/drift, and uncertainty checked for involved nodes?
- [ ] Were raw timestamps preserved, distinguishing event time from ingestion time?
- [ ] For JFR/GC/traces/metrics, are durations or aggregation windows represented accurately?
- [ ] Does the timeline cross-check at least two independent evidence types (IDs, stacks/event types/metrics)?
- [ ] Does the conclusion clearly separate **certain facts**, **estimates**, and **open assumptions**?

**Self-check exercise:** Node A runs `+120 ms` fast relative to reference time and logs a request at `08:14:05.370Z`; well-synced node B logs GC at `08:14:05.400Z`; GC uptime is `905400 ms`, JVM start `07:59:00Z`. Convert A's request to `08:14:05.250Z`, keep GC at `08:14:05.400Z`; the estimated timestamp gap is **150 ms**. If A's offset is known only within `+120 ±40 ms`, ordering and precision claims must factor in uncertainty rather than claiming millisecond certainty. You also need GC pause and request evidence to confirm timeout cause.

## References

- Oracle, [Java SE 17 — `java` command and Unified JVM Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): decorators `utctime`, `uptime`, `uptimemillis`, `timemillis`, `timenanos`, `-Xlog`.
- Oracle, [Java SE 17 — `System.currentTimeMillis()` and `System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): distinguishing wall clock and elapsed clock.
- Oracle, [Java SE 17 — `RuntimeMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/RuntimeMXBean.html): `getStartTime()` and `getUptime()`.
- Oracle, [Java SE 17 — `java.time`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): `Instant`, `OffsetDateTime`, `LocalDateTime`, and `ZonedDateTime`.
- Oracle, [Java SE 17 — JFR events](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html): event timestamps and durations.
- systemd, [`journalctl` manual](https://www.freedesktop.org/software/systemd/man/latest/journalctl.html): `short-iso-precise` and `short-monotonic` formats.
- Prometheus, [PromQL functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `time()`, `timestamp()`, and metric windows.
- OpenTelemetry, [Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): `Timestamp` and `ObservedTimestamp`; [Tracing API](https://opentelemetry.io/docs/specs/otel/trace/api/): start/end timestamps, span duration.

When investigating real incidents, preserve **raw values + normalized UTC + clock origin + instance identity + uncertainty**. A timeline with tidy timestamp order yet missing those five elements easily produces wrong conclusions.
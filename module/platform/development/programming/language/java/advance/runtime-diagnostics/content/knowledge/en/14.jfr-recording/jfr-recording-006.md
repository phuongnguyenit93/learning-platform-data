# 14.6 Tuning Event `enabled`, `threshold`, `period`, and `stackTrace` in JFR

## 1. Learning to Control JFR Evidence

Java Flight Recorder (JFR) records **events** about the JVM and application: GC, CPU, threads, locks, I/O, allocations, class loading, and application-defined events. You should not enable every event type at maximum detail by default: the data can grow huge, make analysis harder, and increase monitoring overhead. Conversely, overly tight settings can miss the exact phenomenon under investigation.

The four core settings of an **event type** are:

- `enabled`: whether that event type is recorded.
- `threshold`: minimum duration required to retain a **duration event**.
- `period`: emission/sampling cadence for a supporting **periodic event**.
- `stackTrace`: whether to record the call stack alongside the event.

These are **event settings**. They differ from **recording options** such as `name`, `duration`, `filename`, `disk`, `maxsize`, and `maxage`, which control the lifecycle and storage of the entire recording. One JVM can host multiple recordings; interpreting data requires knowing the event type, recording, JDK, and effective configuration.

Example problem: request p99 spikes sharply and you suspect threads are waiting long on locks. Instead of enabling everything, you can enable `jdk.JavaMonitorEnter`, set `threshold=20 ms` to focus on significant waits, enable `stackTrace=true` to locate code call sites, and also capture periodic CPU with `jdk.CPULoad#period=1 s`. Then inspect the actual logs/output to confirm whether you captured what you expected.

Scope: JDK 17+ with syntax and API illustrated per JDK 21. Event names, defaults, and setting descriptors vary across JDKs/builds. A setting not supported by an event type does not magically take effect just because you write it into a configuration.

## 2. Exact Meaning Table

| Setting | Meaning | Example Values | Do Not Confuse With |
| --- | --- | --- | --- |
| `enabled` | Enables or disables recording that event type | `true`, `false` | Does not turn the entire JVM or JFR on/off |
| `threshold` | Drops events whose duration is **less than** the threshold | `0`, `10 ms`, `1 s` | Not events per second or application timeout |
| `period` | Cadence for periodic/sampling events | `20 ms`, `1 s`, `everyChunk` | Not a duration filter for lock/I/O events |
| `stackTrace` | Captures stack trace at emission/commit point if applicable | `true`, `false` | Not distributed tracing or automatic root-cause analysis |

### 2.1. `enabled`

When `enabled=false`, JFR does not record that event type into recordings using that configuration. Real Java activity still happens: threads still wait on locks, CPU still runs, I/O still executes. `true` is only a necessary condition: if no activity emits the event, the threshold filters everything out, or the recording misses the failure window, you can still get 0 events.

Example:

```text
jdk.JavaMonitorEnter#enabled = true
jdk.CPULoad#enabled = true
```

Do not treat "default enabled=true" in `jdk.jfr` docs as proof that every JDK event is present in a file. Default annotations may be overridden by `default.jfc`, `profile.jfc`, or recording creation flags. Always inspect the **effective settings** of the specific recording.

### 2.2. `threshold`

This is a **duration filter** for event types that support thresholds. `threshold=20 ms` means an 8 ms event is dropped, while a 45 ms event is eligible to be recorded if `enabled=true` and no other condition excludes it. `threshold=0` means no minimum duration limit is enforced.

Sensible scenarios:

- `jdk.JavaMonitorEnter#threshold=20 ms`: focus on relatively long monitor waits.
- `jdk.FileRead#threshold=50 ms`: find slow file reads, then use stack traces to identify callers.
- Custom duration event `demo.Operation#threshold=25 ms`: record application operations taking at least around 25 ms.

A threshold does not change how long operations take; it only governs what gets recorded. If 10,000 operations each taking 5 ms add up to large total latency, `threshold=100 ms` can leave the file nearly empty of those events even though the app is genuinely slow. Setting it too low, conversely, can record too many events and stacks.

Standard syntax in the Java API: `"20 ms"`, `"1 s"`; supported units include `ns`, `us`, `ms`, `s`, `m`, `h`, and `d`. On the CLI, space-less values like `20ms` are typically accepted. Do not write bare numbers without knowing how the parser interprets units.

### 2.3. `period`

`period` applies to **periodic events** or sampling events that declare this setting. `jdk.CPULoad#period=1 s` requests CPU samples roughly every one second. An execution sampling event can have its own period to adjust sample density.

The value `everyChunk` means emitting per JFR data chunk cycle, **not every exact N milliseconds**. Even with `1 s` or `20 ms`, expect jitter from scheduling/implementation; this is a target cadence, not a hard real-time clock.

You cannot use `period` to turn `jdk.JavaMonitorEnter` into a ticker emitted every second: that event represents monitor waits, not a periodic metric. To catch long waits, use `threshold`. To track CPU trends, use `period` on the appropriate event.

### 2.4. `stackTrace`

`stackTrace=true` instructs JFR to save the Java call stack for supporting event types. For custom events emitted via `Event.commit()`, the stack trace is captured at the commit point; for JVM-provided events, stack capture position depends on the event type. Stacks help attribute call sites, though they do not explain an entire request chain or causes outside the JVM.

`stackTrace=false` still allows recording other fields: timestamps, duration, thread, payload, and event-specific metadata. Disabling stacks can lower overhead and size, at the expense of making it harder to trace which code held a lock or performed slow I/O.

Whether stack trace overhead is large or small depends on **event count**, stack depth, how the JVM samples, and runtime configuration. A handful of stacks on long contention episodes is usually helpful; millions of tiny events with stacks can create heavy noise.

## 3. Distinguishing Duration Events and Periodic Events

The two mechanisms can be pictured as follows:

```text
Duration event (lock, file read, custom operation)
    activity occurs -> produces event with duration
          |
          +-- enabled=false ------------------> not recorded
          |
          +-- duration < threshold -----------> not recorded
          |
          +-- meets criteria -----------------> record fields/duration
                                                   |
                                                   +-- stackTrace=true -> attach stack if supported
```

```text
Periodic/sampling event (e.g., jdk.CPULoad)
    enabled=true
          |
          +-- period=1 s -> request emission roughly every second
          |
          +-- collect sample/stats -> record event if sampled and criteria met
```

These are conceptual diagrams, not internal JFR implementation blueprints. The analysis rule remains: **`threshold` filters each event's duration; `period` governs periodic/sampling cadence**.

| Operational Question | Suitable Event | Key Settings |
| --- | --- | --- |
| Where are threads waiting over 20 ms on `synchronized`? | `jdk.JavaMonitorEnter` | `enabled=true`, `threshold=20 ms`, `stackTrace=true` |
| Did CPU spike during a 10-minute window? | `jdk.CPULoad` | `enabled=true`, `period=1 s` |
| Which file reads lasted over 50 ms? | `jdk.FileRead` | `enabled=true`, `threshold=50 ms`, `stackTrace` as needed |
| Suspecting brief CPU hotspots | `jdk.ExecutionSample` | `enabled` and `period` if allowed by event descriptor |
| Want to record custom business tasks over 25 ms | `demo.Operation` | `enabled=true`, `threshold=25 ms`, `stackTrace=true` |

The values above are starting points, not "optimal settings" for every service. Measure event counts, file size, CPU, and latency impact when tuning.

## 4. Event Setting Syntax and Effective Configuration

### 4.1. `event#setting` Key Format

Per the JFR API, keys combine the full event name and setting name separated by `#`:

```text
jdk.JavaMonitorEnter#enabled=true
jdk.JavaMonitorEnter#threshold=20 ms
jdk.JavaMonitorEnter#stackTrace=true
jdk.CPULoad#enabled=true
jdk.CPULoad#period=1 s
```

In `.jfc`, each setting sits inside an `<event name="...">` element. In `jfr configure` or `JFR.start` commands, use `event#setting=value`, usually writing `20ms` without spaces. In the Java API, a map uses key `"jdk.CPULoad#period"` and value `"1 s"`.

If an event class shares a name across multiple classloaders, the API also supports `<event-id>#<setting>`. Event IDs are meaningful only within the current JVM instance, so never hardcode numeric IDs across environments.

### 4.2. Not Every Event Supports All Four Settings

Query `EventType.getSettingDescriptors()` on a real JVM. Duration events typically expose `threshold`; periodic events like `jdk.CPULoad` typically expose `period`. Never assume every event has `stackTrace` or `period`. A custom event does not automatically become periodic simply because you pass a period setting.

Similarly, some events have specialized settings or use distinct sampling mechanisms. Read exact names and default settings from the JDK itself. This metadata reflects **event type capabilities**, while the actual recording config can override defaults.

### 4.3. Configuration Layers

- **Class annotations** such as `@Enabled`, `@Threshold`, `@Period`, and `@StackTrace` provide the event type's defaults when declared.
- **JFC files** (`default.jfc`, `profile.jfc`, or custom variants) define the settings loaded into a recording.
- **Start command overrides** via `-XX:StartFlightRecording` or `jcmd ... JFR.start` can set values taking precedence over the JFC for the new recording.
- **Java API** calls like `Recording.enable(...).with...` and `Recording.setSettings(...)` configure a programmatically managed recording.

`default.jfc` is built for low-cost continuous recording; `profile.jfc` gathers richer data and typically suits short profiling sessions. Do not edit standard JFC files inside `JAVA_HOME/lib/jfr`: create a new file for easy comparison and reproducibility. Each recording has its own configuration; with multiple concurrent recordings, total JVM overhead can add up.

## 5. Creating a JFC Configuration with `jfr configure`

### 5.1. Generating a File from the Default Profile

JDK 19+ recommends `jfr configure` to generate configuration files. Example (run in a writable directory):

```bash
jfr configure --output diagnostics.jfc jdk.JavaMonitorEnter#enabled=true jdk.JavaMonitorEnter#threshold=20ms jdk.JavaMonitorEnter#stackTrace=true jdk.CPULoad#enabled=true jdk.CPULoad#period=1s
```

When `--input` is omitted, the tool uses the default configuration as its base. The resulting `diagnostics.jfc` retains other template settings while replacing the specified ones. If an event is not yet present in the template, `jfr configure` supports adding it with a `+` prefix before the event name; check `jfr help configure` in your JDK.

Conceptually, the corresponding XML sections look like:

```xml
<event name="jdk.JavaMonitorEnter">
    <setting name="enabled">true</setting>
    <setting name="threshold">20 ms</setting>
    <setting name="stackTrace">true</setting>
</event>
<event name="jdk.CPULoad">
    <setting name="enabled">true</setting>
    <setting name="period">1 s</setting>
</event>
```

This is only a **snippet**, not a complete JFC file; a real file requires a wrapping `<configuration ...>` element and the other events if preserving template settings.

### 5.2. Recording JFR on a Running JVM

Identify the JVM PID:

```bash
jcmd -l
```

Run the example below, **replacing PID 12345 and paths with real values**; use absolute paths for services/containers to avoid directory confusion:

```bash
jcmd 12345 JFR.start name=lock_diagnostics settings=diagnostics.jfc duration=2m filename=lock_diagnostics.jfr
jcmd 12345 JFR.check name=lock_diagnostics verbose=true
```

`JFR.start` creates the recording with the chosen settings. `JFR.check verbose=true` lets you inspect the recording's event settings **while it is still active**. Never rely solely on "Started recording"; verify the right JVM/PID and effective settings.

You can quickly override settings at start time:

```bash
jcmd 12345 JFR.start name=lock_short settings=default duration=60s filename=lock_short.jfr jdk.JavaMonitorEnter#enabled=true jdk.JavaMonitorEnter#threshold=10ms jdk.JavaMonitorEnter#stackTrace=true
```

On the CLI, each `event#setting=value` pair is one token; durations like `10ms` are written without spaces so the shell does not split them into two arguments. Overrides apply to the new recording and do not implicitly alter other active recordings.

To stop early and export the file:

```bash
jcmd 12345 JFR.stop name=lock_diagnostics filename=lock_diagnostics.jfr
```

Do not run `stop` again after the recording has already finished via `duration`. `jcmd` attach commands require appropriate permissions; behavior can differ between a JVM inside a container and a process on the host.

### 5.3. Inspecting the File to Verify Results Instead of Trusting Config

```bash
jfr summary lock_diagnostics.jfr
jfr print --events jdk.JavaMonitorEnter lock_diagnostics.jfr
jfr print --events jdk.CPULoad lock_diagnostics.jfr
jfr print --stack-depth 20 --events jdk.JavaMonitorEnter lock_diagnostics.jfr
```

`jfr summary` displays counts of each event type recorded in the file; `jfr print` filters specific events. `--stack-depth 20` only controls how many frames are **displayed** from already-recorded stacks; it cannot recover uncaptured frames.

For example, finding zero `jdk.JavaMonitorEnter` events has several possible causes: no contention occurred, all waits were below threshold, the recording missed the incident window, the event was disabled, or you inspected the wrong JVM/file. **Zero events does not prove "there is no lock issue."**

Once you have the file, JDK Mission Control (JMC) helps correlate time-series stats, group stack traces, and view charts alongside GC/CPU/threads. Keep timing metadata, configuration, and workload consistent when comparing before and after.

## 6. Runnable Java 17+: Custom Event + Periodic Event

A custom event does not automatically emit on a `period`; the application must instantiate and `commit` it. The program below records a duration event named `demo.Operation` for two operations with a 25 ms threshold and stacks enabled, while also enabling the periodic `jdk.CPULoad` event to illustrate an independent `period`.

Create **`JfrSettingsDemo.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Enabled;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;

public final class JfrSettingsDemo {
    @Name("demo.Operation")
    @Label("Demo operation")
    @Category({"Demo", "Diagnostics"})
    @Enabled(false)
    @Threshold("0 ms")
    @StackTrace(false)
    public static final class OperationEvent extends Event {
        @Label("Operation name")
        public String operation;
    }

    private static void measure(String name, long milliseconds)
            throws InterruptedException {
        OperationEvent event = new OperationEvent();
        event.operation = name;
        event.begin();
        Thread.sleep(milliseconds);
        event.end();
        event.commit();
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("jfr-settings-demo.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(OperationEvent.class)
                    .withThreshold(Duration.ofMillis(25))
                    .withStackTrace();

            recording.enable("jdk.CPULoad")
                    .withPeriod(Duration.ofSeconds(1));

            recording.start();
            measure("fast", 1);
            measure("slow", 80);
            Thread.sleep(1200);
            recording.stop();
            recording.dump(output);
        }

        System.out.println("Recording completed");
    }
}
```

Compile and run:

```bash
javac JfrSettingsDemo.java
java JfrSettingsDemo
jfr summary jfr-settings-demo.jfr
jfr print --events demo.Operation jfr-settings-demo.jfr
jfr print --events jdk.CPULoad jfr-settings-demo.jfr
```

**Stdout of the Java program itself when file writing succeeds:**

```text
Recording completed
```

`jfr summary`/`jfr print` produce output that varies by machine, JDK version, scheduling, and recorded data; there is no fixed transcript to copy. Under normal conditions, `slow` exceeds 25 ms and is retained, whereas `fast` (~1 ms) is filtered out. `Thread.sleep` does not guarantee exact latency on a heavily loaded machine, so do not assert the event count is always 1.

Key points explained:

1. `@Enabled(false)`, `@Threshold("0 ms")`, and `@StackTrace(false)` define the custom event class's defaults.
2. `recording.enable(OperationEvent.class)` enables the event in the recording being created; `withThreshold(Duration.ofMillis(25))` and `withStackTrace()` override the defaults for this recording.
3. `event.begin()` and `event.end()` measure duration; `event.commit()` submits the event for JFR evaluation. `Event.shouldCommit()` can help avoid constructing expensive payloads when an event will not be recorded.
4. `recording.enable("jdk.CPULoad").withPeriod(...)` configures **a separate periodic event**; it does not turn `OperationEvent` into a periodic event.
5. Custom event stacks are captured at the `commit` point. To attach accurate business context, populate payloads and choose commit sites carefully; a single stack does not replace end-to-end request tracing.
6. `stop()` ends the recording; `dump(output)` saves the file for inspection; `try-with-resources` closes the recording. The file may contain sensitive runtime information and requires proper access control.

### 6.1. Replacing the Entire Settings Map with `Recording.setSettings`

The Java API also supports:

```java
// Fragment used where a recording variable of type jdk.jfr.Recording is already available.
recording.setSettings(java.util.Map.of(
    "demo.Operation#enabled", "true",
    "demo.Operation#threshold", "25 ms",
    "demo.Operation#stackTrace", "true",
    "jdk.CPULoad#enabled", "true",
    "jdk.CPULoad#period", "1 s"
));
```

This is an **illustrative fragment, not a standalone program**. `setSettings` **replaces the entire settings map** of the recording: passing only a single entry can accidentally erase other existing settings. When modifying just a few options, chaining `enable(...).with...` is usually clearer and safer. You can inspect a recording's settings map with `recording.getSettings()`.

## 7. Querying Settings Actually Supported by an Event Type

No need to guess setting names: `FlightRecorder.getEventTypes()` and `EventType.getSettingDescriptors()` let you ask the JVM directly. Create **`ListJfrSettings.java`**:

```java
import java.util.Set;
import jdk.jfr.EventType;
import jdk.jfr.FlightRecorder;
import jdk.jfr.SettingDescriptor;

public final class ListJfrSettings {
    public static void main(String[] args) {
        Set<String> targets = Set.of(
                "jdk.JavaMonitorEnter", "jdk.CPULoad");

        for (EventType type
                : FlightRecorder.getFlightRecorder().getEventTypes()) {
            if (!targets.contains(type.getName())) {
                continue;
            }
            System.out.println(type.getName());
            for (SettingDescriptor setting
                    : type.getSettingDescriptors()) {
                System.out.println("  " + setting.getName()
                        + " = " + setting.getDefaultValue());
            }
        }
    }
}
```

```bash
javac ListJfrSettings.java
java ListJfrSettings
```

Output order and lines depend on the JDK and event type list and are not fixed. Confirm that `jdk.JavaMonitorEnter` exposes `threshold`/`stackTrace` and `jdk.CPULoad` exposes `period`. `SettingDescriptor.getDefaultValue()` is the **event type's** default; it is not a promise that an active recording retains that exact value. Inspect recording settings via `Recording.getSettings()` or `jcmd ... JFR.check verbose=true`.

If a custom event class is loaded across multiple classloaders, carefully distinguish event name from event ID. Never hardcode numeric IDs across runs.

## 8. Setting-Tuning Strategy for Root-Cause Investigation

Suppose p99 latency increases and you suspect monitor contention:

1. **Formulate a concrete hypothesis:** are long individual lock waits slowing requests, or are huge numbers of short waits adding up?
2. **Pick the right events:** `jdk.JavaMonitorEnter` for monitor contention; if suspecting CPU, also check `jdk.ExecutionSample` and `jdk.CPULoad`; if suspecting I/O, pick `jdk.FileRead`/`jdk.SocketRead` as appropriate.
3. **Set an initial level:** for a long-lock hypothesis, try `enabled=true`, `threshold=20 ms`, and `stackTrace=true` for a short 1–2 minute capture during the incident.
4. **Verify effectiveness:** `JFR.check verbose=true` before stopping, then `jfr summary` and `jfr print` after dumping. Do not mix data across multiple PIDs/recordings.
5. **Adjust if missed:** if 0 events appear while requests remain slow, verify you picked the right event first; then consider lowering the threshold in a new capture, or investigating another cause.
6. **Correlate with context:** JFR timelines, request traces, CPU, thread dumps, GC pauses, thread pools, and OS/container metrics.
7. **Measure overhead:** events/sec, recording size, CPU, disk I/O, and latency impact; keep the lowest level sufficient to explain the phenomenon.
8. **Document configuration and results:** JDK version, collector, workload, timestamps, settings, event counts, and attempted changes.

| Change | Benefit | Trade-off |
| --- | --- | --- |
| `enabled=false → true` | Allows capturing the relevant event type | Increases cost/volume; may still yield 0 events if untriggered |
| `threshold=100 ms → 5 ms` | Reveals more short duration events | Larger files; more stacks if enabled |
| `threshold=0 → 50 ms` | Focuses on long operations | Hides cumulative impact of many short operations |
| `period=1 s → 20 ms` | Finer sampling on supporting events | Sampling overhead; still does not guarantee catching every spike |
| `stackTrace=false → true` | Adds code context | Can significantly raise overhead on high-frequency events |
| `stackTrace=true → false` | Less data/cost | Lacks caller context during analysis |

To compare two recordings, keep workload, resource limits, and JDK identical with comparable durations. Compare rates **per unit time**, duration distributions, and stack locations rather than comparing raw counts across files of different lengths.

## 9. Common Conceptual and Configuration Errors

**Error 1: Using `period` as `threshold`.** `jdk.CPULoad#period=1 s` controls how often CPU info is recorded; `jdk.JavaMonitorEnter#threshold=1 s` keeps only lock waits lasting at least roughly 1 second. They do not share a meaning of "one event per second."

**Error 2: Using `threshold` on an unsupported periodic event.** If an event type does not declare that setting, use the proper setting (typically `period`). `jfr configure` does not turn an unsupported setting into a new mechanism.

**Error 3: Concluding there is no problem because event count is 0.** The threshold might be too high, the recording at the wrong time/PID, the event disabled, or no matching activity occurred in the window. Verify trigger conditions before concluding.

**Error 4: Enabling all events and stack traces without checking overhead.** Prioritize events that test your hypothesis; change small groups at a time and watch `jfr summary`, CPU, disk, and latency.

**Error 5: Reading only default annotations.** JFC configurations and recording overrides decide what is actually recorded. `@Enabled(true)` does not prove a JFR file contains the event.

**Error 6: Treating `Recording.setSettings(Map.of(...))` as a single-key update.** This API **replaces** the entire map rather than merging; use `EventSettings` or build a new map preserving the options you want to keep.

**Error 7: Seeing missing stacks and increasing `jfr print --stack-depth`.** Printing cannot invent frames that were never recorded. Capture a new recording with `stackTrace=true` if the event supports it and your investigation requires it.

**Error 8: Calling `jcmd JFR.configure` expecting to change every event in a running recording.** `jfr configure` creates JFC files; `JFR.start` selects settings for a new recording; `jcmd`'s `JFR.configure` manages JVM-level JFR options and is not equivalent to calling `Recording.setSettings` on an existing recording.

## 10. Self-Check Questions

**Question 1.** You need to find monitor waits over 30 ms along with Java call sites. What should you use?

*Answer:* Choose `jdk.JavaMonitorEnter` and try `enabled=true`, `threshold=30 ms`, `stackTrace=true`. Check event descriptors first, capture during the failure window, and correlate with threads/request traces.

**Question 2.** You need a CPU trend every 2 seconds for 10 minutes; should you set `threshold=2 s` on `jdk.CPULoad`?

*Answer:* No. Use `jdk.CPULoad#period=2 s` if supported by the event; `threshold` does not describe the cadence of this event.

**Question 3.** With `enabled=true` and `threshold=100 ms`, `jfr summary` shows 0 `jdk.FileRead` events; can you conclude all file I/O is fast?

*Answer:* No. There could be many file reads under 100 ms, the recording may have missed load, or it may be the wrong JVM/file. To be sure, check the capture window, settings, and possibly lower the threshold in a new capture.

**Question 4.** Does setting `stackTrace=true` when recording periodic CPU load guarantee an execution flame graph?

*Answer:* No. CPU load is a periodic statistic; to analyze where CPU time is spent, use appropriate execution sampling/profiling events and check their stack support.

**Question 5.** When a custom event declares `@Enabled(false)`, can it be enabled via the Java API?

*Answer:* Yes. `recording.enable(CustomEvent.class)` can enable it in that recording; class-level annotations act as a baseline that can be overridden.

## 11. Checklist When Handing Over a JFR Recording

- [ ] Document **JDK/build**, JVM/PID, start/end timestamps, recording name, and filename.
- [ ] Distinguish event settings from recording options.
- [ ] Verify the event type exists and which of `enabled`, `threshold`, `period`, `stackTrace` it supports.
- [ ] Use `threshold` for duration events and `period` for periodic/sampling events.
- [ ] Record whether stack traces are enabled or disabled, and do not expect reader tools to recover uncaptured data.
- [ ] Know configuration precedence: annotations → JFC → CLI or Java API overrides.
- [ ] Use `JFR.check verbose=true` or `Recording.getSettings()` to inspect effective settings.
- [ ] Use `jfr summary`/`jfr print` to verify data was actually collected.
- [ ] Correlate events with request timelines, CPU/GC/threads/I/O, and workload.
- [ ] Check overhead, event counts, recording size, and retention/storage policies.

**Core principle:** `enabled` answers *should this event type be recorded?*; `threshold` answers *how long must a duration event last to be kept?*; `period` answers *at what cadence is a periodic event emitted/sampled?*; `stackTrace` answers *should call stacks be attached to locate code?*. Proper settings matter only when verified on the **actual recording** and framed around a concrete diagnostic question.

## References

- Oracle JDK 21 — [`jdk.jfr` package: Settings and configuration](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
- Oracle JDK 21 — [`EventSettings` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html).
- Oracle JDK 21 — [`Recording` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- Oracle JDK 21 — [`jfr` command: configure/print/summary](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- Oracle JDK 21 — [`jcmd` command: JFR.start/check/stop](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- Dev.java — [Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/jfr/configure/).
- Oracle JDK 21 — [Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html).
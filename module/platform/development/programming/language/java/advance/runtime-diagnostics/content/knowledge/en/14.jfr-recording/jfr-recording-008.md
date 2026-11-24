# 14.8 Understanding Missing Data Due to Disabled Events, Thresholds, or Data Loss

## Objectives

A Java Flight Recorder (JFR) recording **lacking the event you are looking for** does not prove that the corresponding activity never occurred. Between actual application behavior and the data you read in a `.jfr` file lie multiple stages of selection, filtering, buffering, retention, and extraction. Missing data may be completely faithful to configuration, yet it can also steer an investigation to the wrong conclusion.

After this lesson, you will be able to:

1. Explain why an event may be absent because it was **disabled**, **below threshold**, **sampled periodically**, **outside the recording window**, or **dropped/no longer retained**.
2. Inspect active configurations with `jcmd ... JFR.check verbose=true` and inspect files with `jfr summary`, `jfr metadata`, and `jfr print`.
3. Choose events, thresholds, and recording durations aligned with your goal, then re-capture data capable of answering the question.
4. Distinguish "event not seen," "no stack trace," "not storing full history," and "data lost while recording."
5. State conclusions with calibrated confidence: **no trace seen in this recording** differs from **proving the incident did not occur in the system**.

This lesson uses command names and APIs matching **HotSpot/OpenJDK Java 17+** JFR, referencing JDK 21 usage. Event names, available event sets, and `default`/`profile` template contents should be verified on the **exact JDK/version being run**.

## 1. Which "Gates" Does JFR Data Pass Through?

JFR records **events** with a name/type, timestamp, and descriptive fields. Duration events typically include a duration; some events carry a thread or stack trace. Depending on the event type, the JVM or application must actually trigger and commit the event before the engine has data to collect.

Conceptual pipeline:

```text
Behavior occurs in the JVM/application
    |
    v
Does a matching event type and emission mechanism exist?
    |
    v
Is the event enabled in the relevant recording?
    |
    v
Does the event pass filters/threshold/period/sampling?
    |
    v
Event is written to JFR buffers/chunks
    |
    v
Is the data still retained within the time/size window?
    |
    v
Did dump/export target the right recording and time range?
    |
    v
Does the analysis tool show the right event type/filters?
```

At **any step**, the event can disappear from your output. That is why you must pinpoint where data went missing before tuning the JVM or changing code.

| Observed Symptom | Possible Mechanism | What You Cannot Conclude Yet |
| --- | --- | --- |
| No `jdk.JavaMonitorEnter` in file | Event disabled, no qualifying lock contention, duration below threshold, or wrong window | Cannot conclude the app never uses `synchronized` or has zero contention |
| Events exist but lack stack traces | `stackTrace=false`, stack not captured at that point, or display limits stacks | Cannot conclude the event did not happen |
| Few CPU/Execution Samples | Periodic/probabilistic sampling, not a log of every method invocation | Cannot compute exact method call counts from sample counts |
| File covers only recent time | `maxage`/`maxsize` evicted older parts, `disk=false` held only an in-memory window, or dump was bounded | Cannot conclude earlier times were incident-free |
| Gaps in metrics under heavy load | Buffers, chunk writes, I/O, abrupt exit, or capture/read errors caused missing data | Cannot treat "0 events" as absolute proof |

## 2. Case 1 — Event Not Enabled

JFR ships two configuration templates with the JDK: `default.jfc` prioritizes low overhead, while `profile.jfc` captures additional data for deeper analysis. **Neither template enables every event**, and active settings may have been customized or overridden when starting the recording.

Each event type commonly supports these settings:

| Setting | Effect |
| --- | --- |
| `enabled=true/false` | Whether that event is permitted to be recorded |
| `threshold` | For duration events, keeps only events meeting the duration criterion |
| `period` | For periodic events, requested emission cadence |
| `stackTrace=true/false` | Whether to request capturing a stack trace with the event |

Beyond general settings, there are event/JDK-specific options such as sampling or throttling policies. Do not assume every event has a meaningful `threshold` or `period`.

Specifically, **an event type appearing in `jfr metadata` does not prove an instance was recorded**. Metadata describes the schemas/types known to the recording; actual instance counts must be checked via summaries and event data.

### Checking a running recording

Obtain the PID of the real Java process:

```bash
jcmd -l
jcmd 12345 JFR.check
jcmd 12345 JFR.check name=diagnostics verbose=true
```

Replace `12345` with the real PID. `diagnostics` is an **illustrative** recording name; if that recording does not exist, check the list from `JFR.check` and use the active name/ID. With `verbose=true`, HotSpot can print the recording's current event settings. For exact syntax on your JDK:

```bash
jcmd 12345 help JFR.check
jcmd 12345 help JFR.start
```

Cross-check **event type, right recording, and right time**. A recording's settings can change while running; `JFR.check` reflects the state at check time, not a guarantee that the entire history used those exact settings. Once a recording stops, keep the `.jfc` config and launch commands used for collection.

### Focusing on a missing event

For example, to observe how long threads actually wait to **enter a Java monitor**, `jdk.JavaMonitorEnter` is relevant. Simply entering a `synchronized` block does not guarantee emitting this event: the corresponding behavior—specifically actual monitor contention—must occur.

If you care about short waits, check `jdk.JavaMonitorEnter#enabled` and `jdk.JavaMonitorEnter#threshold`. Never use the absence of events to prove "no lock contention" before checking both settings.

## 3. Case 2 — Event Enabled but Below Threshold

`threshold` specifies that **duration events shorter than the threshold are not recorded**. Consider a monitor contention setup:

- `jdk.JavaMonitorEnter#enabled=true`
- `jdk.JavaMonitorEnter#threshold=20ms`

Suppose within one window four contention episodes last 3 ms, 8 ms, 14 ms, and 36 ms. Assuming all belong to this event type and no other data loss occurs, those **under 20 ms** are filtered out; the 36 ms event can appear. Only the slow tail remains, no longer representing all contention episodes.

| Actual Behavior | Configuration | Expected Result in File |
| --- | --- | --- |
| Contention lasting 8 ms | `threshold=20ms` | Event not recorded |
| Contention lasting 36 ms | `threshold=20ms` | Eligible to be recorded |
| Contention lasting 8 ms | `threshold=0ms` | Eligible if event enabled and other conditions met |
| Event recorded with `stackTrace=false` | Event enabled | Event may appear, without an attached stack |

Lowering the threshold can sharply increase event count and overhead. `0ms` is useful for **short-window reproduction**, not for running indiscriminately on heavily loaded systems just to "have everything." Also, changing the threshold after recording cannot surface previously filtered events: you must **capture a new recording**.

### Distinguishing `threshold` from `period` and sampling

- **Threshold** filters by duration on eligible events (such as blocked I/O or monitor contention).
- **Period** sets the emission interval for statistical/periodic events like `jdk.CPULoad`. One sample per second does not describe every fluctuation between seconds.
- **Execution sampling** observes stacks only at sampling points. A method absent from samples does not prove it never ran; sample counts do not equal invocation counts.
- **Stack trace setting** governs attached stack data, not whether the event itself occurred.

Two recordings using different periods or thresholds **should not have raw event counts compared as if coverage were identical**. A drop in `JavaMonitorEnter` count after raising the threshold may simply mean fewer were recorded.

## 4. Case 3 — Data Lost or No Longer in Retained Storage

We must separate two distinct things often lumped together as "data loss."

### 4.1. Data never fully persisted during recording

JFR passes data through thread-local buffers and global buffers/chunks. Under intense activity or constrained write resources, some data may not be persisted completely. A JVM crash or abrupt shutdown can also leave unflushed buffer data out of the file.

Signs to cross-check:

- Event volume surging after enabling many detailed events or very low thresholds.
- JVM/JFR logs reporting errors or warnings about writing recordings, buffers, repository, or data loss (exact messages vary by JDK).
- File does not cover the full observed time span, or data shows abnormal gaps.
- Reader tools report file/chunk errors, or the recording was truncated by an abrupt process exit.

**Not every JDK version and scenario writes an obvious "data loss" event into the file.** Seeing no data-loss indicator likewise does not prove 100% of events were captured. When real data loss is suspected, cross-check logs, files, time spans, recorder settings, and system metrics. Do not invent lost byte/event counts from a chart gap without a reliable counter.

### 4.2. Data once recorded but evicted by retention policy

Long-running recordings can operate as a **sliding window**. When `maxage` (data age) or `maxsize` (retained size) is exceeded, older chunks can be discarded to keep newer ones.

With `disk=false`, a recording does not maintain full history in a disk repository like `disk=true`; in-memory buffers have finite capacity and may hold only a recent interval. This is **retention policy**, distinct from a disabled event or buffer-overflow loss.

For example, an operator wants to investigate a 10:00 failure, but waits until 11:00 to dump a recording configured to retain only the last 20 minutes: the file can be completely valid while **no longer containing 10:00 data**. Increasing `maxage` afterward cannot restore evicted chunks.

Additionally, `JFR.dump` can slice time ranges and cap export volume via `begin`, `end`, `maxage`, or `maxsize`; viewer tools also have time filters. An empty target window in a file can therefore stem from **extracting the wrong slice**, even if the original recording had the data.

### Quick distinction table

| Cause | Can Old Data Be Recovered from the Current File? | Remediation |
| --- | --- | --- |
| Event disabled during incident | No | Re-capture with the right event enabled, if reproducible |
| Threshold dropped event at commit | No | Lower threshold appropriately and re-capture |
| Sampling/period missed the moment | Cannot reconstruct unsampled events | Increase resolution or supplement with other metrics |
| Data dropped / write error | Cannot faithfully reconstruct missing parts from incomplete file | Fix pipeline/overhead, cross-check other sources, re-capture |
| Old chunks evicted by `maxage`/`maxsize` | No from current dump; only if an earlier copy was saved | Raise retention **before** incident window; dump promptly |
| Export/dump or UI filter applied | Potentially still in full recording if retained | Target right recording, clear filters, or dump again |
| Missing stack trace | Event itself may still be present | Enable `stackTrace` and re-capture when call-site analysis is needed |

## 5. Inspect `.jfr` Files Before Inferring

Two layers need verification: the **running recording** and the **dumped artifact**. They do not automatically match if settings changed or export filters were applied.

### 5.1. Capturing a clearly named and windowed recording

For example, on Java 17+ with no suitable recording running yet, after confirming PID `12345`:

```bash
jcmd 12345 JFR.start name=diagnostics settings=profile disk=true duration=120s filename=diagnostics.jfr
jcmd 12345 JFR.check name=diagnostics verbose=true
```

This command **starts a new recording in a running JVM**, not running a Java file. `settings=profile` uses a built-in template and generally captures more data than `default`; it does not guarantee your needed event is enabled or its threshold fits. A 120-second window helps only if the error reproduction **occurs within that window**.

To grab a snapshot before the recording auto-stops:

```bash
jcmd 12345 JFR.dump name=diagnostics filename=diagnostics-now.jfr
```

`JFR.dump` writes data to disk while **the running recording continues running**. Verify actual path, timestamps, start/stop times, and PID. If the command fails, do not mistake an older file with the same name for a fresh capture.

### 5.2. Reading the file with `jfr`

The following commands read an existing file without altering originally recorded events:

```bash
jfr summary diagnostics-now.jfr
jfr metadata --events jdk.JavaMonitorEnter diagnostics-now.jfr
jfr print --events jdk.JavaMonitorEnter diagnostics-now.jfr
```

- `jfr summary` reports duration and statistics on event types and counts **stored in the file**. It is the starting point for telling whether "one type is missing" or "the whole window" has an issue.
- `jfr metadata` shows event type and field descriptions; **having metadata does not mean instances exist**.
- `jfr print --events ...` prints only events matching the filter; empty output alone does not prove the event never happened. Verify exact full event name, right file, and any active filters.
- In GUI tools like JDK Mission Control, also check **time range**, event type selection, thread filters, and aggregation mode. An empty chart may simply be a filtered view.

If unsure of exact event names:

```bash
jfr metadata diagnostics-now.jfr
jfr summary diagnostics-now.jfr
```

Use the exact event name you find to run `jfr print`. Because the JDK defines many event types, `metadata` output can be long; inspect selectively for your problem.

### 5.3. How Should "No Event Found" Be Stated?

Insufficient: "JFR shows no monitor contention, so the app has no contention."

More accurate conclusion:

> In `diagnostics-now.jfr` from the inspected JVM, within the retained time range, zero `jdk.JavaMonitorEnter` instances were found. Contention shorter than the threshold, outside the window, missed by sampling/loss, or belonging to a different event type cannot yet be ruled out. Verify active settings and reproduce with a suitable threshold.

Once you have confirmed the event is enabled, threshold is appropriate, the window covers the workload, and no signs of data loss exist, confidence increases—yet still document **JFR's observation limits** in your report.

## 6. Enabling the Right Event/Threshold with a Custom Configuration

When the target is clearly very brief monitor contention, build a custom template based on `default.jfc`. Example in Bash/Linux/macOS with `JAVA_HOME` pointing to a full JDK:

```bash
jfr configure --input "$JAVA_HOME/lib/jfr/default.jfc" \
  --output contention-debug.jfc \
  "jdk.JavaMonitorEnter#enabled=true" \
  "jdk.JavaMonitorEnter#threshold=0ms" \
  "jdk.JavaMonitorEnter#stackTrace=true"
```

`jfr configure` creates `contention-debug.jfc` and **does not automatically apply to existing recordings**. For a new capture:

```bash
jcmd 12345 JFR.start name=contention-check settings=contention-debug.jfc \
  duration=60s disk=true filename=contention-check.jfr
jcmd 12345 JFR.check name=contention-check verbose=true
```

After running a workload that triggers real contention and writing the file, inspect:

```bash
jfr summary contention-check.jfr
jfr print --events jdk.JavaMonitorEnter contention-check.jfr
```

Keep in mind:

1. **The commands above use Bash shell syntax.** On Windows PowerShell, pass the actual JDK `.jfc` path and run on a single line or use PowerShell line continuation; do not copy Bash `\` line continuations verbatim.
2. `threshold=0ms` raises the chance of capturing short contention, yet it cannot turn an unemitted event into a real one, nor guarantee complete capture under overload.
3. Event stack traces show the stack at capture time per event semantics; they can raise overhead and file size.
4. Do not apply threshold 0 and stack traces across all events in production for long periods without measuring overhead.
5. To observe periodic events or execution sampling, adjust **`period`/the sampling mechanism of that specific event**, rather than mechanically applying `threshold`.

## 7. Java 17+ Experiment: Proving Absence via `enabled` and `threshold`

The standalone program below creates **three sequential recordings** in the same JVM with a custom event. Each recording commits one event, yet only the first case is saved. The example intentionally uses a **one-day** threshold for an event of near-zero duration so the outcome does not depend on `sleep` precision.

```java
// File: JfrSettingsDemo.java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

public class JfrSettingsDemo {
    @Name("demo.Work")
    public static class Work extends Event {
        public String label;
    }

    private static long record(String label, boolean enabled, Duration threshold)
            throws Exception {
        Path file = Files.createTempFile("jfr-settings-demo-", ".jfr");
        try (Recording recording = new Recording()) {
            if (enabled) {
                recording.enable(Work.class).withThreshold(threshold);
            } else {
                recording.disable(Work.class);
            }
            recording.start();

            Work event = new Work();
            event.label = label;
            event.begin();
            event.end();
            event.commit();

            recording.stop();
            recording.dump(file);
        }
        try {
            return RecordingFile.readAllEvents(file).stream()
                    .filter(e -> e.getEventType().getName().equals("demo.Work"))
                    .count();
        } finally {
            Files.deleteIfExists(file);
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("enabled=" + record("visible", true, Duration.ZERO));
        System.out.println("disabled=" + record("disabled", false, Duration.ZERO));
        System.out.println("threshold=" + record("filtered", true, Duration.ofDays(1)));
    }
}
```

On JDK 17+ with the standard `jdk.jfr` module, save as **exact filename `JfrSettingsDemo.java`**, then run:

```bash
javac JfrSettingsDemo.java
java JfrSettingsDemo
```

Expected stdout; compiled and verified on OpenJDK 24:

```text
enabled=1
disabled=0
threshold=0
```

Explanation:

- **`enabled=1`**: custom event `demo.Work` is enabled with threshold 0; one committed event is present in the first file.
- **`disabled=0`**: the exact same `event.commit()` call runs, yet the recording is configured not to collect that event type.
- **`threshold=0`**: the event is enabled and committed, yet its tiny duration falls below the one-day threshold, so it does not appear in the third file.

Temporary `.jfr` files are created in the OS temp directory and deleted after counting; this is an API demonstration, not a simulation of **buffer-overload data loss**. To simulate a suspected real failure, use a real workload and recording while measuring latency, request counts, and recording size.

**Key takeaway:** two zeroes look identical in `jfr summary`, yet their **causes differ**. You cannot use a zero alone to guide code fixes or conclude no behavior occurred.

## 8. Investigation Workflow When JFR Is Missing Data

### Step 1 — Define precisely what you expected to see

Be specific: "I expected `jdk.FileRead` during slow file reads around 14:20–14:25," or "I expected contention over 2 ms," rather than just saying "JFR is missing logs." Record JDK, OS, build, PID/container, and how workload was generated.

If you suspect the **event type does not match the behavior**—for instance checking `JavaMonitorEnter` when the issue is `LockSupport.park` or I/O—pick the right event/metric instead of forcing thresholds on the wrong event.

### Step 2 — Confirm the recording actually ran at the right time

Check `JFR.check`, recording name, `delay`, `duration`, start/stop times, time zones, and incident time. If `duration` expired or `delay` had not elapsed, events outside the recording cannot appear. If the failure precedes recorder activation, start earlier on the next reproduction.

### Step 3 — Check "what was enabled," not just "which profile name was used"

Read `JFR.check verbose=true` while running; save the `.jfc` file/start command and inspect actual event settings. Never assume `settings=profile` enables everything. If multiple recordings exist, confirm which one was dumped; do not mix up PIDs or names.

### Step 4 — Check threshold, period, sampling, and stack trace

If an event type has instances but too few: inspect threshold, period, and sampling behavior. If events exist without stacks: check `stackTrace` and tool display/`--stack-depth`, rather than assuming events were lost.

### Step 5 — Check output data and retention

Run `jfr summary` on the file to inspect actual start/end times, event counts, and size; check `maxage`/`maxsize`, `disk`, `begin`/`end` at dump time, file write errors, abrupt stops, and tool filters. When long history is needed, design retention ahead of incidents: repository capacity, rolling window, dump timing, and storage directories with ample space.

### Step 6 — Formulate an evidence-based data-loss hypothesis

Suspect recorder loss only when signals exist such as log warnings/write errors, abnormal missing intervals, incomplete files, event rates exceeding write capacity, or divergence from an independent source. Missing events due to **threshold** are intentional filtering; old data evicted by **retention** is storage policy; name each issue accurately.

### Step 7 — Re-capture with verifiable coverage

Enable only events needed for your question, choose a low-enough threshold, use a short window and reproducible workload; consider adding resources or trimming noisy events to curb overhead. Repeat at least twice if symptoms fluctuate. If data is missing from event streaming/dashboards, check the **raw JFR file** before blaming the producer.

### Step 8 — Record conclusions alongside limits

Examples:

- "`jdk.JavaMonitorEnter` did not appear because the recording had `enabled=false`; must re-capture, no evidence exists regarding contention at that earlier time."
- "`jdk.FileRead` had a 20 ms threshold, so this file reflects only sufficiently slow I/O; do not use event count as total read count."
- "The file retains only the last 15 minutes, so an incident 45 minutes ago cannot be verified from this artifact."
- "Evidence shows write errors/missing chunks during X–Y; do not use data in that interval to conclude the phenomenon was absent."

## 9. Quick Decision Table by Symptom

| Symptom | Priority Check | Appropriate Action |
| --- | --- | --- |
| `jfr print --events X` is empty | Exact name X, `jfr summary`, recording window, `enabled` | Enable X or pick right event and re-capture if needed |
| Metadata has event type, summary has 0 instances | `enabled`, whether event triggered, threshold, time window | Do not treat metadata as proof of capture |
| Event appears only when tasks are very slow | `threshold` on duration event | Lower threshold in a controlled way |
| Statistical events are very sparse | `period` or sampling | Increase resolution if cost is acceptable |
| Events present but stacks empty/short | `stackTrace`, stack depth, and viewer settings | Re-capture with `stackTrace` or adjust display |
| File missing the opening minutes | `maxage`/`maxsize`, `disk=false`, dump range | Adjust retention **before reproduction** |
| Corrupt file/chunk or abnormal gap | JVM/JFR logs, storage, buffers, process crashes | Fix write error, trim event volume, re-capture |
| Dashboard empty while `jfr print` shows events | Time filter, event type, thread filter, ingest pipeline | Fix filter/ingest, keep raw file intact |
| File captured fully yet count is below request count | Event is not 1:1 with requests, filters/sampling, timestamps | Determine denominator and event→request mapping |

## 10. Mistakes to Avoid

1. **"No events means no errors."** True only when you have proven the event would be emitted and captured under those exact conditions; in practice rarely sufficient for an absolute negative claim.
2. **"Profile enables everything."** `profile.jfc` has its own scope and thresholds; inspect your JDK and recording settings.
3. **"A 20 ms threshold means sub-20 ms issues did not happen."** They may well have happened, simply excluded from the file by the filter.
4. **"Counting execution samples equals counting method calls."** Sampling is statistical observation, not complete execution tracing.
5. **"JFR metadata has the schema, so data must exist."** Schema is not instances.
6. **"Missing stack trace means lost event."** Separate uncaptured payload fields from unrecorded events.
7. **"`JFR.dump` recovers everything that ever happened."** Dump exports only what remains in the recording within the extracted slice; filtered/lost/evicted parts cannot be recreated.
8. **"Increasing `maxsize` after the incident recovers history."** It does not restore evicted chunks.
9. **"Just enable all events at threshold 0—it's free."** Dense recording raises overhead/data volume and can even obscure analysis.
10. **"An empty file proves the JVM was idle."** Verify PID, recording name, time, artifact path, time filter, and event type first.

## 11. Handover Checklist for a JFR Recording

- [ ] Include exact PID/JDK/build/JFR recording name and timestamps.
- [ ] Know `delay`, `duration`, start/stop times, and when the workload ran.
- [ ] Verified `enabled` plus `threshold`/`period`/sampling of the target event.
- [ ] If stack traces are needed, checked `stackTrace` and display limits.
- [ ] Ran `jfr summary`, inspected metadata/event counts, and verified the right file.
- [ ] Cross-checked `disk`, `maxage`, `maxsize`, dump window, and repository path.
- [ ] Checked for recorder/write errors or process crashes; did not assume zero data loss.
- [ ] Included at least one independent measurement for major conclusions (logs/requests/metrics/GC/OS), especially if JFR data is sparse.
- [ ] Conclusion explicitly separates **what was observed**, **what cannot yet be inferred**, and how to re-capture to verify.

**Conclusion:** "No event seen" is the result of **a configured and bounded observation**, not an automatic negation of application behavior. Check sequentially: **right event → `enabled` → `threshold`/`period`/sampling → recording window → buffer/retention → dump and analysis filters** before explaining gaps in JFR.

### Official References

- Oracle JDK 21 — `jdk.jfr` event settings (`enabled`, `threshold`, `period`, `stackTrace`): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle JDK 21 — `jcmd` (`JFR.start`, `JFR.check`, `JFR.dump`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — `jfr` tool (`summary`, `metadata`, `print`, `configure`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Dev.java — configuring recordings and `.jfc`: https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/

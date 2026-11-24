# 14.2 Distinguishing Continuous Recordings from Fixed-Duration Recordings

## Learning Objectives

Java Flight Recorder (JFR) records JVM and application events such as GC, class loading, CPU sampling, thread activity, allocation samples, or I/O (depending on event configuration). When investigating runtime issues, deciding between **continuous recording** and **fixed-duration recording** directly affects whether the minutes leading up to an incident are preserved, how many resources are consumed, and when you receive the `.jfr` file for analysis.

After this lesson, you will be able to:

1. Explain the lifecycle of a **continuous recording** and a **fixed-duration recording**, especially the relationship between runtime duration, retained data, and file export timing.
2. Accurately distinguish JFR parameters: `duration`, `delay`, `settings`, `disk`, `maxage`, `maxsize`, `filename`, `dumponexit`; understand their limits and interactions.
3. Use `jcmd` to start, check, dump, and stop recordings in a controlled manner; understand why **dump does not mean stop**.
4. Choose the right mode for the need: tracing rare incidents, long-term monitoring, hotspot investigation, regression checks, or capturing short evidence around an experiment.
5. Avoid pitfalls such as only setting `filename` and assuming a continuous file is already ready, letting the repository grow unbounded, running `profile` long-term without measuring cost, or expecting an already-ended fixed recording to capture a subsequent incident.

Scope: HotSpot/OpenJDK Java 17+; operational syntax illustrated using JDK 21 `jcmd`/JFR. Supported configurations and events may vary across JDKs/vendors. In every case, verify using the `help` command on the target JVM itself.

## 1. Two Different Concepts: Recording Lifecycle and Data Retention Time

A **JFR recording** is an event-collection session with a name/ID, event configuration, and lifecycle state. A **`.jfr` file** is the exported data saved for preservation and opened in Java Mission Control (JMC), the `jfr` tool, or compatible analysis systems. While recording with `disk=true`, JFR may use a temporary **disk repository** to hold chunks; the repository is not an evidence file guaranteed to remain forever.

A recording has three milestones to keep separate:

- **Collection start:** when the recording transitions to running, possibly after a `delay`.
- **Collection end:** due to reaching `duration`, a `stop` operation, or process/JVM termination.
- **Data export:** a `JFR.dump` while still running, `JFR.stop` with `filename`, automatic write upon `duration` expiry when `filename` is set, or dump-on-exit behavior if conditions allow.

In a continuous recording, collection can run for many hours or days, while the retained data is typically only the **most recent window** bounded by `maxage` or `maxsize`. In a fixed-duration recording, JFR stops collecting after `duration`, but the output file is only created/written successfully if an appropriate save mechanism is chosen and write permissions/space exist.

**Do not confuse how long a recording has been active with the time span contained in a dump file.** A session running for 24 hours that retains at most 30 minutes can provide only the final window before the dump; it does not contain all 24 hours.

## 2. Direct Comparison

| Criterion | Continuous Recording | Fixed-Duration Recording |
| --- | --- | --- |
| How to start | Omit `duration` or set `duration=0s` (on JDK 21 `jcmd`) | Set a positive `duration`, e.g., `duration=2m` |
| When it stops | Runs until stopped, JVM exits, or external intervention | Automatically stops after `duration`; can also be stopped early |
| Primary goal | Keep recent history to investigate hard-to-reproduce incidents | Capture details within a known window |
| Retained data | Usually bounded by `maxage`/`maxsize`, discarding older chunks | Usually retains the span from start to stop; setting retention limits may drop the beginning |
| Producing an analysis file | `JFR.dump` when an incident occurs, or `JFR.stop` with `filename` | `filename` at `JFR.start` to auto-write on completion; can also dump early |
| Usually sensible settings choice | `default.jfc` or a lightweight configuration with measured overhead | `profile.jfc` or needed deep-dive configuration |
| Operational cost | Accumulates over time; needs retention/disk monitoring | Concentrated in a short window; need to measure CPU/volume/pause overhead |
| Strengths | Can preserve **data from before the incident was detected** | Easy to tie to load tests, operations, hypotheses, and test timing |
| Weaknesses | If not dumped before old data is evicted, lost parts cannot be recovered | Incidents outside the capture window will lack evidence |

**`default` and `profile` do not define continuous vs. fixed.** They are preset configurations of events and recording cost. You can run fixed-duration with `settings=default` and continuous with `settings=profile`, provided that choice has a clear reason and its own overhead measurements.

## 3. Continuous Recording Mechanism: A "Black Box" Keeping the Most Recent Window

### 3.1. Lifecycle and Rolling Retention

When `JFR.start` omits `duration`, the default `duration=0s` means running indefinitely until stopped or the VM terminates. With `disk=true`, events are assembled into chunks and written to the repository. `maxage` and `maxsize` limit the **amount of data retained** in the repository for that recording—they are not timers that stop the recording.

- **`maxage=1h`**: retains only recent data up to the age limit; once exceeded, older chunks may be discarded. This is not a guarantee of having an exact hour of data if the recording only started a few minutes ago or is further constrained by `maxsize`.
- **`maxsize=256m`**: limits retained recorded data by size. If the event generation rate is high, 256 MiB may cover only a few minutes; if low, it may cover longer.
- **Setting both `maxage` and `maxsize`**: the remaining dataset is bounded by both. The actual window may be shorter than `maxage`, and retention is managed by chunks rather than cut strictly at second/byte boundaries.
- **Omitting both** with `disk=true`: the recording's data repository can grow in total size over time; you need an operational policy instead of assuming it rotates automatically.
- **`disk=false`**: stores data in memory buffers; disk retention parameters `maxage`/`maxsize` do not apply to this mode on JDK 21 `jcmd`. Do not rely on this mode expecting long pre-incident history.

Timeline example (all numbers illustrative):

| Time | Continuous running, `maxage=30m`, sufficient `maxsize` | Data likely still retained |
| --- | --- | --- |
| 09:00 | Start | Almost none yet |
| 09:10 | Still recording | 09:00–09:10 |
| 10:00 | Still recording | Around 09:30–10:00 |
| 10:07 | Application spikes; dump immediately | Around 09:37–10:07, covering before and during the spike |
| 10:45 | No further dump | Very old data may have been evicted; the 10:07 snapshot, if exported, remains independent evidence |

If `maxsize` is tighter, the window at 10:07 may be shorter than 30 minutes. If the application is killed before a dump occurs, the repository is not guaranteed to survive or remain valid after a restart. These timestamps only illustrate the mechanism, not exact chunk timestamps for every JFR recording.

### 3.2. Continuous Does Not Mean "An Open `.jfr` File Filling Up Forever"

Example `JFR.start` with `filename` and no `duration`:

~~~bash
jcmd "$PID" JFR.start name=watch settings=default disk=true \
  maxage=30m maxsize=256m filename=/var/tmp/jfr/watch-final.jfr
~~~

The recording **keeps running**. `filename` at start defines where the recording is written when the recording stops; continuous data may currently reside in the temporary repository. To capture a snapshot immediately without turning off the "black box", use `JFR.dump` with a different output path. Do not wait until stop if you want to preserve evidence of an incident that already happened.

### 3.3. When to Choose Continuous?

Suitable when:

- Latency, CPU, GC, or contention incidents appear sporadically and are usually detected **after** they have already occurred.
- You need at least several minutes of history before and after an alert to identify the mechanism.
- Long-running services want baseline telemetry and the ability to dump on incident.
- Retention monitoring, disk capacity, write permissions, export/collection procedures, and an overhead budget are clearly in place.

**Costs to evaluate:** event selection, event stack traces, sampling rate, chunk size, CPU/I/O, repository space, and impact on the workload itself. `settings=default` is usually a lightweight starting point for continuous recording. Never claim "JFR overhead is zero"; measure actual overhead under representative load.

## 4. Fixed-Duration Mechanism: Recording with a Defined Start and End

When specifying `duration=2m`, the recording is scheduled to end roughly 2 minutes after collection starts. If `delay` is set, the JVM waits for the delay before recording; `delay` does not capture data "before start time". When the duration is reached, the recording ends; if a suitable `filename` is provided, data is written to the target file per command behavior.

Example:

~~~bash
jcmd "$PID" JFR.start name=cpu_probe settings=profile \
  disk=true duration=2m filename=/var/tmp/jfr/cpu-probe-2m.jfr
~~~

Explanation:

1. The command starts session `cpu_probe` with the events in `profile.jfc`.
2. Collection runs for about 2 minutes, unless stopped early or the JVM stops.
3. `filename` is the export destination for the `.jfr` file when the session finishes; immediately after `JFR.start`, the file may **not exist yet or be incomplete**.
4. After successful completion, use `jfr summary`/`jfr print` or JMC to verify that data covers the target window.

Fixed-duration is suitable for:

- Short sampling when latency increases steadily and reproduction timing is known.
- Measuring a specific request mix after warm-up during a load test.
- Investigating CPU methods, allocation hotspots, locks/I/O during a controlled benchmark interval.
- Comparing baseline and candidate runs of the same length, same event settings, and equivalent load.

**Note:** `duration` only governs the lifecycle; it does not guarantee all events are enabled, all stacks are recorded, or no events were dropped. A "2-minute" recording can still reflect only 1 minute of load if the workload under study started late.

### 4.1. Fixed-Duration Can Also Lose the Start of the Window

If you set `duration=30m` while `maxage=5m` or `maxsize` is too small, older data can be evicted while the recording is still running. Thus the statement "fixed duration is guaranteed to keep the whole interval" holds only if retention settings, disk capacity, and export succeed adequately.

To capture the entire interval, align retention or avoid setting caps smaller than needed, and ensure the disk/container has sufficient space. With event-heavy profiles, volume can grow significantly. Do not set "unlimited" values in production merely hoping for a complete file: you need a budget and safeguards against filling the disk.

## 5. Important Parameters and Mistakes to Avoid

| Option | Exact Meaning on JDK 21 `jcmd` | Common Mistake |
| --- | --- | --- |
| `duration=2m` | Automatically stops the recording after about 2 minutes | Confusing it with keeping only the last 2 minutes while running forever |
| `duration=0s` or omit `duration` | Recording does not expire automatically by time | Interpreting `0s` as stopping immediately |
| `delay=15s` | Waits 15 seconds before starting collection | Thinking `delay` captures 15 seconds of prior history |
| `settings=default` | Uses the lightweight `.jfc` config geared toward continuous use | Thinking `default` is a separate recording mode |
| `settings=profile` | Enables a deeper event set, potentially higher cost | Running for days without measuring overhead |
| `disk=true` | Writes data to the disk repository during recording | Thinking `disk=true` immediately creates the final evidence file |
| `maxage=30m` | Maximum age of data retained on disk for the recording | Mistaking it for auto-stopping after 30 minutes |
| `maxsize=256m` | Size limit of retained disk data | Mistaking it for a heap/JVM limit or a guarantee of 30 minutes of data |
| `filename=/path/file.jfr` in `JFR.start` | Output destination when the recording stops | Thinking the file is complete immediately upon start |
| `dumponexit=true` | Attempts to write the recording on JVM shutdown via supported mechanisms | Believing `SIGKILL`/`OOMKilled` is guaranteed to produce a file |
| `JFR.dump name=... filename=...` | Exports a snapshot; the running recording **continues running** | Thinking dump also stops the recording |
| `JFR.stop name=... filename=...` | Stops and writes the target file | Stopping without `filename` and assuming data was saved |

`maxage` and `maxsize` on `JFR.start` apply when `disk=true`. `maxsize` must not be smaller than the maximum chunk size configured via `JFR.configure`. A suffix such as `m` in `duration` means **minutes**, whereas `m` in `maxsize` means **MiB/MB per JVM parser rules**; always read the option context.

### 5.1. JFR Memory Buffers, Repository, and Artifact File Are Three Separate Components

- **In-JVM buffers** hold events prior to flushing; they are not the full history of a continuous recording.
- **Disk repository** consists of temporary data/recording chunks used by the JVM while recording; location is configured via `JFR.configure repositorypath` (version-dependent) and requires a stable filesystem with adequate space.
- **Exported file (`.jfr`)** is produced by dump/stop/duration completion; that is the artifact to preserve and store for incident analysis.

Do not rely on manually copying open chunks out of the repository as a standard backup method. JFR can delete old chunks per retention or clean up the repository on JVM exit. Investigation workflows need a verified export operation.

## 6. Practice A: Continuous Recording and Dumping After an Alert

This is an illustrative Linux shell sequence for Java 17+/JDK 21; these commands interact with a JVM, so run them only against the right service, PID, and permissions. In production, confirm attach is permitted, the storage path is not publicly exposed, and sufficient space is available.

### 6.1. Preparing the Right PID and Evidence Location

~~~bash
java -version
jcmd -l
PID=12345               # Replace with real PID; never use 12345 on a live system
mkdir -p /var/tmp/jfr    # Directory must be writable by the target Java process
jcmd "$PID" help JFR.start
jcmd "$PID" help JFR.dump
~~~

Run `jcmd` from the same host/container appropriate for the JVM and with an effective user/group that satisfies attach requirements. Filenames are resolved on the filesystem in the target process's context; check mounts/volumes/permissions. Do not confuse a PID in the host namespace with the PID seen inside a container.

### 6.2. Starting Continuous Once

~~~bash
jcmd "$PID" JFR.start name=service_watch \
  settings=default disk=true maxage=1h maxsize=256m
jcmd "$PID" JFR.check name=service_watch
~~~

Starting without `duration` keeps the recording running. Check with `JFR.check` to verify the exact name/ID and state. When running continuously, record the start timestamp, Java version, event configuration, `maxage`/`maxsize`, and actual disk usage. Do not start additional recordings with the same name on every alert; check existing sessions first.

### 6.3. When an Alert Fires, Dump the Most Recent Window

~~~bash
jcmd "$PID" JFR.dump name=service_watch \
  filename=/var/tmp/jfr/watch-incident.jfr maxage=15m
jcmd "$PID" JFR.check name=service_watch
jfr summary /var/tmp/jfr/watch-incident.jfr
~~~

`JFR.dump` creates a snapshot of currently retained data, optionally bounded to an export window (here at most the last 15 minutes). The `service_watch` recording **remains active** after the dump; a subsequent alert can request a second snapshot. If you need to analyze before/after a spike, dump close enough to the event; do not wait until rolling retention evicts older data.

Within the same incident, keep distinct files by timestamp and instance to avoid overwriting filenames. Naming it `watch-incident.jfr` here is only illustrative; in practice, include time/PID/instance in filenames and operational records.

### 6.4. When You Actually Want to End the Continuous Recording

~~~bash
jcmd "$PID" JFR.stop name=service_watch \
  filename=/var/tmp/jfr/watch-final.jfr
~~~

Stop is a state-changing operation: afterward `service_watch` no longer collects new events. Stopping without `filename` risks discarding un-dumped data depending on command behavior; when you need an artifact, specify `filename` explicitly and verify file completion. Do not stop a continuous recording just to inspect one snapshot if you still want observability for the next incident.

**Distinguish the three outcomes:**

- `JFR.check`: inspects active sessions (does not export a file).
- `JFR.dump`: exports a copy of retained data; session stays active.
- `JFR.stop`: ends the session, optionally exporting a file if `filename` is specified.

## 7. Practice B: Fixed-Duration for a Scheduled Experiment

For example, suppose you want to measure 2 minutes after the service has warmed up, using the same hypothetical PID and directory:

~~~bash
jcmd "$PID" JFR.start name=load_test_2m \
  settings=profile disk=true duration=2m \
  filename=/var/tmp/jfr/load-test-2m.jfr
jcmd "$PID" JFR.check name=load_test_2m
~~~

After the duration ends and export finishes:

~~~bash
jfr summary /var/tmp/jfr/load-test-2m.jfr
jfr print --events jdk.GarbageCollection /var/tmp/jfr/load-test-2m.jfr
~~~

`jfr print` here illustrates filtering one event type, printing only events actually present in the file. Absence of matching events does not prove the system had no GC; check event settings and recording span. Waiting in this example is an observation condition—do **not** run arbitrary blocking commands in production.

If load only begins after 1 minute and the recording stops after 2 minutes, the file contains only one minute of useful experiment data. Synchronize with warm-up, workload stabilization, start/stop points, and application log markers. You can use `delay=15s` to schedule startup, but account for the delay in the test timeline.

### 7.1. Can You Dump a Fixed-Duration Recording Before It Expires?

~~~bash
jcmd "$PID" JFR.dump name=load_test_2m \
  filename=/var/tmp/jfr/load-test-interim.jfr
~~~

While running, this creates an interim snapshot and the recording continues until `duration` or `stop`. If a severe incident occurs before the duration expires, an early snapshot preserves evidence; events occurring after the dump point cannot retroactively appear in the older snapshot file.

### 7.2. When Should You Explicitly Stop Early?

You can use:

~~~bash
jcmd "$PID" JFR.stop name=load_test_2m \
  filename=/var/tmp/jfr/load-test-early-stop.jfr
~~~

Use this only while the recording is **still running** and you want to stop it early; if it has already stopped automatically at `duration`, `JFR.stop` may report that no active recording exists. Do not execute both an early stop and waiting for automatic completion as if both were mandatory steps in one workflow.

## 8. Practice C: Configuring JFR at JVM Startup

You cannot always attach after an incident occurs. Startup options let you collect data from application boot, which is useful for slow startup or incidents occurring as soon as traffic arrives.

### 8.1. Continuous from Startup

~~~bash
java -XX:StartFlightRecording=name=startup_watch,settings=default,disk=true,maxage=1h,maxsize=256m \
  -jar app.jar
~~~

This startup configuration launches a recording with no duration limit, keeping a rolling window. `app.jar` is only an example name; use your actual path and service launch command. Provision repository space and a `JFR.dump` mechanism to extract evidence.

### 8.2. Fixed-Duration from Startup

~~~bash
java -XX:StartFlightRecording=name=startup_probe,settings=profile,duration=2m,filename=/var/tmp/jfr/startup-probe.jfr \
  -jar app.jar
~~~

The recording ends after roughly two minutes of collection and writes the file if the JVM is still running and has write permissions/space. This is a bounded way to capture warm-up/startup; if an error happens at minute 8, this recording cannot contain data from that moment.

### 8.3. Role of `dumponexit`

You can set `dumponexit=true` so the JVM tries to write the recording on shutdown; however, **clean shutdown differs from abrupt termination**. `SIGKILL`, `OOMKilled`, host loss, filesystem errors, or crashes can prevent the JVM from completing file output. For incidents needing reliable evidence, continuous recording plus verified periodic/alert-triggered dumps is a better strategy than relying solely on `dumponexit`.

## 9. Practice D: Java 17+ API Demonstrating Both Modes

Besides `jcmd`, Java provides an API in module `jdk.jfr` to manage `Recording` instances. The standalone program below demonstrates the difference between **taking a snapshot while still recording** and **stopping automatically after a duration**. The example creates files in the current working directory; run it in an environment with a full JDK and file write permissions.

Create the file **`JfrModesDemo.java`**:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;
import jdk.jfr.RecordingState;

public class JfrModesDemo {
    public static void main(String[] args) throws Exception {
        try (Recording continuous =
                     new Recording(Configuration.getConfiguration("default"))) {
            continuous.setName("continuous-demo");
            continuous.setToDisk(true);
            continuous.setMaxAge(Duration.ofMinutes(10));
            continuous.setMaxSize(128L * 1024 * 1024);
            continuous.start();

            Thread.sleep(1200);
            continuous.dump(Path.of("continuous-snapshot.jfr"));
            System.out.println("Continuous snapshot saved");
        }

        try (Recording fixed =
                     new Recording(Configuration.getConfiguration("profile"))) {
            fixed.setName("fixed-demo");
            fixed.setToDisk(true);
            fixed.setDuration(Duration.ofSeconds(3));
            fixed.setDestination(Path.of("fixed-result.jfr"));
            fixed.start();

            while (fixed.getState() == RecordingState.RUNNING) {
                Thread.sleep(100);
            }
            System.out.println("Fixed recording finished");
        }
    }
}
~~~

Compile and run:

~~~bash
javac --add-modules jdk.jfr JfrModesDemo.java
java --add-modules jdk.jfr JfrModesDemo
jfr summary continuous-snapshot.jfr
jfr summary fixed-result.jfr
~~~

The stdout produced by the `System.out.println` statements when both sessions and file writes succeed:

~~~text
Continuous snapshot saved
Fixed recording finished
~~~

The two subsequent `jfr summary` commands print **reports that vary by environment**, so their stdout is not mocked here. The two `.jfr` files are real artifacts produced by the program.

Behavior explanation:

- `continuous` starts without setting a duration; after about 1.2 seconds, `dump` writes a snapshot. Closing `Recording` via try-with-resources ends the example; in a real service, a continuous session is kept running much longer.
- `fixed` uses `setDuration(3 seconds)` and `setDestination`. It finishes automatically when the time elapses; the loop waits until `RecordingState` is no longer `RUNNING`. Because a destination is set, the result is written/closed according to API semantics.
- Very short durations in seconds only serve to test the API—they are **not useful capture windows for drawing performance conclusions**. In production, evaluate event configuration, overhead, permissions, read/write cycles, and lifecycle instead of copying illustrative durations verbatim.

**Do not mix up the two APIs:** `setDuration` sets the collection session limit; `setMaxAge` and `setMaxSize` limit retained data. `dump(Path)` exports a copy without implicitly changing the duration. Calling `close` on an experimental recording cleans up resources; it is not equivalent to "guaranteed final file saved" if neither `dump` nor `setDestination` completed.

## 10. Distinguishing Recorded Data from Sufficient Evidence to Conclude

The recording mode only answers **when** and **how long data is kept**. Evidence quality also depends on the following factors:

### 10.1. Event Settings

- **`default.jfc`**: an event set geared toward routine observation with relatively low cost; suitable as a continuous baseline.
- **`profile.jfc`**: captures richer, deeper data, typically suited for short windows; verify actual CPU/size overhead.
- **Custom `.jfc`**: selects events, thresholds, stack traces, and sampling periods based on a hypothesis; document and version configurations to compare sessions.

If you need allocation profiling, contention, or a specific I/O event that the configuration has not enabled, extending `duration` will not make a disabled event appear. Before and after an experiment, inspect `JFR.check` verbose output (if supported) and `jfr summary` reports to know which events the file contains.

### 10.2. Sampling and Representativeness

JFR can record both exact events and sampled events. "No CPU samples found for method X" is not enough to conclude X did not run. Check the recording span, load, sample counts, thresholds, event settings, and stack truncation. Avoid interpreting 20 seconds of startup as the steady-state performance of a multi-hour service.

### 10.3. Timeline Alignment

When investigating p99, GC, or CPU spikes:

- Align timestamps across JFR, application logs, APM, and system metrics; use the same time zone/UTC when comparing.
- Record recording start and end times, build version, JDK, PID/pod, JFR configuration, and CPU/memory limits.
- Add markers from load tests/incidents to the timeline; to analyze root causes, retain the minutes **before** the spike as well.
- Avoid comparing a quiet 20-minute baseline against a 2-minute profile at peak load and drawing conclusions solely from higher event counts.

### 10.4. Retention Does Not Guarantee Capturing the Whole Incident

A continuous recording with `maxage=30m` can lose the beginning if an incident lasts 2 hours and the dump is late. A 2-minute fixed-duration recording misses a rare incident occurring at minute 20. When a scenario requires both pre-incident and post-incident data, you can pair a lightweight continuous recording with a fixed/profile recording triggered on alert, while controlling total overhead; multiple recordings share JFR infrastructure and are not completely independent in cost.

## 11. Choosing a Mode by Practical Scenario

| Investigation Question | Initial Choice | Rationale and Proper Capture Approach |
| --- | --- | --- |
| "Yesterday p99 spiked randomly, but we cannot reproduce it." | Lightweight continuous with sufficient retention; dump immediately on alert | Needs history from before a human notices |
| "Running a 5-minute load test to compare CPU hotspots before/after a code change." | Fixed-duration, controlled `profile` | Defined window and load; compare equivalent event settings |
| "Issue appears after several hours of uptime." | Continuous from startup, sufficiently long rolling window | A 2-minute fixed recording at startup usually misses it |
| "Want to measure slow startup during the first 90 seconds." | Fixed from startup | Window aligns with startup lifecycle, easy to analyze |
| "Want to investigate GC pauses during unpredictable spikes." | Continuous + GC logs/APM + dump on spike | Snapshot retains minutes before and after the alert |
| "Only need higher sampling detail for the current 3 minutes." | Fixed/`profile` alongside lightweight continuous if budget allows | Avoids raising overhead of the all-day continuous recording |
| "Service might be abruptly `OOMKilled`." | Continuous with verified proactive/periodic dumps | `dumponexit` is not guaranteed to survive `SIGKILL` |
| "Need to record every event for a full week and retain all of it." | Dedicated budget/archival design; segmented capture/export windows | A single rolling continuous recording cannot guarantee retaining a whole week |

### Illustrative Scenario 1: Dumping Too Late

Continuous configured with `maxage=15m` and sufficient `maxsize`; an alert fires at 10:00, but the on-call engineer dumps at 10:40. By then, the relevant data from 09:50–10:00 may have already been evicted. JFR did not "lose data randomly"; retention worked according to policy. Adjust the retention window to match real detection and response times, or automate fast dumps on alerts and protect artifacts.

### Illustrative Scenario 2: Fixed-Duration Has Data but Misses the Phenomenon

An experiment starts a fixed JFR at 14:00 with `duration=2m`; the load test runs from 14:01:50 to 14:05. The file captures only about 10 seconds of actual load during the recording window. CPU hotspots do not show up because most of the load ran after the recording ended. Fix the synchronization workflow: complete warm-up before starting the fixed recording, emit markers or use an appropriate delay, and run load within the window.

### Illustrative Scenario 3: Prolonged `profile` Changes Application Behavior

A team enables `settings=profile` continuously during peak hours on a tail-latency-sensitive service without checking CPU/disk usage. High-rate events and stack traces can increase overhead or repository size, causing measurements to diverge from baseline. Redesign: lightweight continuous `default`, short fixed `profile`, and controlled A/B overhead comparison. **The recording configuration itself can be an experimental variable.**

## 12. Safe Operations: Storage Location, Capacity, Security, and Verification

### 12.1. Capacity and Retention

Before enabling long-term recording:

1. Estimate JFR event generation rate under peak workload, not just average traffic.
2. Choose `maxage` and `maxsize` to match the required lookback window and disk budget.
3. Check `repositorypath`, write permissions, chunk size, and remaining free space; `maxsize` must be valid relative to max chunk size.
4. Put disk/I/O alert thresholds, cleanup policies for dumped `.jfr` artifacts, and off-container storage in place as needed.
5. Validate with a start/dump/read cycle: the file opens, contains expected timestamps/events, and retention behaves as designed.

**The final `.jfr` file and the repository both consume storage** at certain moments; do not count `maxsize` alone and assume disk usage cannot exceed that budget. Multiple recordings, metadata, exported dump files, and other logs all contribute to disk usage.

### 12.2. Paths and Permissions

The `filename` path given to `jcmd` may be interpreted by the target JVM on its own filesystem. If you attach from a host into a container or use containers with different mounts, a path that exists in the operator shell might not exist or be writable for the JVM. Output files may sit in an ephemeral filesystem lost on pod restart, so a dedicated volume/collector may be needed. Avoid filename collisions and verify file size/timestamps after export.

### 12.3. Protecting Data Inside Recordings

JFR files can contain class names, thread names, stack traces, file paths, endpoint patterns, environment metadata, custom code event payloads, and sensitive operational details. Restrict read/share permissions, set artifact retention, and avoid uploading to public systems. Do not use `jfr print` to spew thousands of events to an uncontrolled console.

### 12.4. Quick Check That a File Is Usable

~~~bash
jfr summary /var/tmp/jfr/watch-incident.jfr
jfr metadata /var/tmp/jfr/watch-incident.jfr
~~~

`jfr summary` reads the time range and counts of recorded events; `jfr metadata` describes the event types in the file's metadata. Check **actual events** in `summary`/`print`—do not infer from metadata event types that those events occurred. If the expected window or events are missing, review timing, settings, rotation/retention, paths, and write permissions.

## 13. Troubleshooting Common Errors

| Symptom | What to Check | Remediation |
| --- | --- | --- |
| PID not found in `jcmd -l` | Process/container namespace, attach permissions, JDK/JRE image | Target the right PID in the same environment, with proper user and JDK tools |
| `JFR.start` reports duplicate name or wrong recording | `JFR.check` across all recordings | Use unique names or act on the already-running recording |
| `JFR.dump` reports no recording | Recording ended, PID changed, JFR was not started | Verify current state; do not assume an old recording survived a restart |
| Start succeeds but no file appears immediately | `filename` on `JFR.start` applies at stop; session has not finished | Use `JFR.dump` for a snapshot or wait for `duration` to finish |
| `maxage=1h` but only a few minutes appear | Small `maxsize`, recently started, high event rate, some chunks evicted | Read actual span from the file; check retention and event rate |
| Repository fills disk | Missing or oversized `maxage`/`maxsize`, multiple recordings/dumps | Tune retention policy with measurements and clean up artifacts per procedure |
| `.jfr` file cannot be opened | File write incomplete, wrong path, truncated, insufficient permissions | Verify dump completion, file size, and `jfr summary` |
| Expected CPU/GC events missing | Settings did not enable event type, sampling/threshold, wrong capture window | Inspect `.jfc`, `jfr summary`/`print`, and load timeline |
| Stopped but no file found | `JFR.stop` without `filename`, wrong path/permissions | When saving is needed, specify `filename` and verify output |
| No dump after `OOMKilled` | `SIGKILL` prevents JVM shutdown hooks from running | Capture evidence proactively before failure; inspect OS/container events |
| Fixed-duration loses the beginning despite sufficient `duration` | `maxage`/`maxsize` capped retained data | Increase retention with justification or shorten `duration` to fit budget |
| JFR increases CPU/I/O | Dense `profile` events, stack traces, concurrent recordings | Use lightweight `default`, bound profiling duration, and measure overhead |

## 14. Checklist Before Choosing and Running

- [ ] I know the question to answer: "already happened unexpectedly" vs. "upcoming controlled experiment."
- [ ] Do I need history **before an alert**, or only data during a scheduled window?
- [ ] I treat recording active time, data retention window, and file export time as three separate concerns.
- [ ] I choose `settings=default`/`profile`/custom based on needed events, with overhead measured/bounded.
- [ ] If continuous: set appropriate disk/retention, know when to `JFR.dump`, and have automated evidence capture.
- [ ] If fixed: set `duration` matching warm-up/load and writable `filename`; ensure retention does not truncate the target window.
- [ ] I know `JFR.dump` **does not stop**, whereas `JFR.stop` **stops** the recording.
- [ ] I have a plan to prevent data loss from `OOMKilled`, pod restarts, disk full, or wrong container paths.
- [ ] I verified JDK/vendor/PID, recording name, and event settings on the actual process.
- [ ] I verify output with `jfr summary` or JMC, confirming the file covers the exact time range under investigation.
- [ ] I have naming, access controls, retention, and sensitive-data handling policies for `.jfr` artifacts.

## 15. Conclusion

**Continuous recording** answers "what happened before the incident was detected?": the session can run indefinitely, maintains a rolling window, and is typically **dumped on demand while continuing to record**.

**Fixed-duration recording** answers "what did the JVM do during this defined experiment window?": the session is given a positive `duration`, stops automatically, and can write a file upon expiry.

Neither mode is inherently more complete than the other. The right choice is the one that delivers the **right data, right time range, and sufficient events, within acceptable overhead and storage limits**, backed by a process to verify that the `.jfr` file is genuinely analyzable.

### References

- Oracle JDK 21, jcmd (JFR.start, JFR.check, JFR.dump, JFR.stop): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Java SE 21, jdk.jfr.Recording API: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Java Flight Recorder API Programmer’s Guide, Flight Recorder Configurations: https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html
- Java 21 JFR command-line tool: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html

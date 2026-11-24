# 14.4. `JFR.check`, `JFR.dump`, `JFR.stop`, and Managing Multiple Recordings

In Java Flight Recorder (JFR), a **recording** is a session that records events about JVM and application activity: CPU, threads, garbage collection, allocations, I/O, or application-defined events. While a service is running, operators usually need three operations: **see which sessions are active**, **export recorded data to a file**, and **end the right session**. The `jcmd` command suite handles those three tasks with `JFR.check`, `JFR.dump`, and `JFR.stop`.

An important scenario is that a single JVM can have **multiple concurrent recordings**. For example, a long-running background recording uses `settings=default`, while a short investigative recording enables `settings=profile`. Using the wrong `name` can export the wrong data, inadvertently mix data from multiple sessions, or stop the recording used for monitoring.

Lesson goals:
- Precisely distinguish the behavior and lifecycle of `JFR.check`, `JFR.dump`, and `JFR.stop`.
- Execute operations against a **specific Java PID** and target the right recording via `name`.
- Understand `verbose`, `filename`, `maxage`, `maxsize`, `begin`, and `end` parameters when needed.
- Manage two concurrent recordings, knowing when to export a snapshot and when to stop to save the final artifact.
- Inspect `.jfr` files with JDK tools and handle common host/container errors.

## 1. Lifecycle Model: Record, Observe, Take Snapshot, End

A typical operational flow:

~~~text
Running JVM
    |
    +-- JFR.start name=baseline ------> [baseline: RUNNING] ----+
    |                                                           |
    +-- JFR.start name=incident ------> [incident: RUNNING] --+ |
    |                                                         | |
    +-- JFR.check --------------------> inspect status only   | |
    |                                                         | |
    +-- JFR.dump name=incident -------> writes incident.jfr   | |  (incident still RUNNING)
    |                                                         | |
    +-- JFR.stop name=incident -------> [incident stopped]    + |
    |                                                           |
    +-- JFR.check --------------------> baseline still RUNNING -+
    |
    +-- JFR.stop name=baseline -------> [baseline stopped]
~~~

| Command | Effect | Does It End the Recording? | When Is a File Created? |
| --- | --- | --- | --- |
| `JFR.start` | Creates/starts a recording | No; starts the session | Can specify an output destination for completion or dump |
| `JFR.check` | Lists recordings and their status/settings | **No** | No |
| `JFR.dump` | Writes a copy of collected data to a `.jfr` file | **No**; the recording continues running | Immediately when the dump succeeds |
| `JFR.stop` | Stops a specified recording | **Yes**, for the selected recording only | If `filename` is passed to save data upon stopping |

Distinguish two artifacts: a **recording** is a lifecycle-managed session inside the JVM; a **`.jfr` file** is the artifact of a single dump/stop. One recording can produce multiple distinct snapshot files while remaining active. Conversely, a written file does not automatically imply a recording is still running.

JFR typically has low overhead with appropriate settings, but it is not zero-cost: `settings=profile` and detailed events can incur higher overhead than `default`. Confirm which commands your target JDK/HotSpot distribution supports via that JVM itself.

## 2. Preparation: Right JVM, Right Permissions, Right Directory

In the examples below, the illustrative PID is **12345**. You **must replace** it with the PID of the real process; commands will not work against a nonexistent PID. On the machine with the JDK:

~~~bash
jcmd -l
jcmd 12345 help JFR.check
jcmd 12345 help JFR.dump
jcmd 12345 help JFR.stop
~~~

- `jcmd -l` lists the Java processes visible to the tool; it is not guaranteed to list JVMs across every process namespace/container.
- `jcmd 12345 help ...` prints the exact syntax of the **target JVM**; option names may vary across JDKs/JVMs.
- Attaching usually requires running on the same host with matching user/group and attach permissions. If attach is disabled, the PID is invisible, or permissions differ, `jcmd` may fail to connect.
- On Linux/containers, prefer an absolute path in an existing directory such as `/var/tmp/jfr/`. `filename` is resolved by the target JVM in the filesystem **where the Java process runs**, not necessarily the filesystem of the terminal invoking `jcmd`.
- JFR files can contain class/method names, stack traces, system properties, paths, and sensitive application data. Protect read permissions, transfer methods, and retention periods.

**Prepare the directory** with permissions for the JVM's user, spare disk capacity, and distinct filenames per capture. The commands below assume `/var/tmp/jfr/` already exists and is writable. On Windows, use a corresponding path such as `C:/jfr/incident.jfr` (after creating the directory).

## 3. `JFR.check`: Seeing Which Recordings Are Active

Basic syntax:

~~~bash
jcmd 12345 JFR.check
~~~

With no arguments, HotSpot JDK 21 displays information about active recordings. The output usually includes **recording ID**, **name**, state, and related configuration/timing details. Exact values depend on the JDK and timing, so do not rely on a fixed stdout example to deduce PID/name.

Inspect only one recording:

~~~bash
jcmd 12345 JFR.check name=baseline
~~~

Inspect along with **event settings**:

~~~bash
jcmd 12345 JFR.check name=baseline verbose=true
~~~

`verbose` defaults to `false`; setting `true` reveals detailed event settings, which is very helpful when wondering why an event type is or is not appearing. Output can be quite long. The command only reads state—it **does not ask the JVM to create a `.jfr` file or stop the session**.

A safe strategy when multiple recordings exist: **always run `JFR.check` right before `dump` or `stop`**, confirming the exact `name`; after `stop`, run it again to verify the other recording is still running.

If it prints "No available recordings", there are no active recordings listable by the command on this JVM. That is not a failure of `check`, nor does it prove the application never produced a `.jfr` file earlier.

## 4. `JFR.dump`: Exporting Data While Continuing to Collect

Command to export a named recording:

~~~bash
jcmd 12345 JFR.dump name=baseline filename=/var/tmp/jfr/baseline-snapshot.jfr
~~~

On success, the JVM writes currently available data from the recording to the file. **`baseline` remains RUNNING after this command**. You can take multiple snapshots at different times, using a new filename each time, and keep collecting events.

Command without `name`:

~~~bash
jcmd 12345 JFR.dump filename=/var/tmp/jfr/all-recordings.jfr
~~~

Per HotSpot JDK 21 documentation, when **`name` is omitted**, `JFR.dump` exports data from **all recordings**. This is intentional tool behavior, though it often surprises operators who intended only one session. With multiple concurrent sessions, always **specify `name`** to scope the export. Even when filtering by name, event settings across concurrent recordings can influence JVM-wide collection data and cost; do not assume they are completely isolated in overhead or event sets.

### 4.1. `filename` and Artifact Identification

`filename` can be a file path or a directory for the JVM to auto-generate a filename. When `filename` is omitted, the JVM can also auto-generate a name from PID/timestamp per JDK 21 docs, though operations are easier to manage when specifying the full path. JDK 21 supports `%p` (PID) and `%t` (timestamp) tokens in filenames, processed by the JFR command.

Example:

~~~bash
jcmd 12345 JFR.dump name=baseline filename=/var/tmp/jfr/baseline-%p-%t.jfr
~~~

This creates a new snapshot—it **does not append data to an existing `.jfr` file**. Do not overwrite the same filename across repeated dumps if you need to keep history; timestamped names also aid comparison.

### 4.2. `maxage` and `maxsize`: Filtering Dump Volume vs. Retention Limits

Example exporting at most the last five minutes from **still-retained** data:

~~~bash
jcmd 12345 JFR.dump name=baseline maxage=5m filename=/var/tmp/jfr/baseline-last5m.jfr
~~~

Example adding a size cap on dumped data:

~~~bash
jcmd 12345 JFR.dump name=baseline maxsize=64m filename=/var/tmp/jfr/baseline-bounded.jfr
~~~

- `JFR.dump maxage=5m` limits the exported time span; it **does not extend the recording's retention window**.
- `JFR.dump maxsize=64m` caps the data exported in that dump, **unlike** `JFR.start maxsize=...` which sets the recording's retention policy.
- If the recording only retains the last 10 minutes of data, requesting a 1-hour dump **cannot recover** data already evicted from storage.
- Limits and chunk boundaries can affect actual exported volume; do not treat `maxsize` as a guarantee that the written file has that exact byte size.

### 4.3. `begin` and `end`: Selecting a Time Range

JDK 21 also supports filtering by **event timestamp** start/end boundaries within the data:

~~~bash
jcmd 12345 JFR.dump name=baseline begin=-15m filename=/var/tmp/jfr/baseline-15m.jfr
~~~

`begin`/`end` accept times parseable as `LocalTime`, `LocalDateTime`, `Instant`, or relative negative offsets with `s`, `m`, or `h` suffixes (e.g., `begin=-30s`). When specifying an absolute range, check time zones and target host clock; `end` must also align with actual data.

**Do not misunderstand:** `begin=-15m` does not mean "start the recording 15 minutes ago." It only **selects the portion of history still available** in the running recording.

### 4.4. Impact of Dumping

`JFR.dump` is documented in JDK 21 as low-impact in normal mode, though it still performs I/O and consumes disk space. The `path-to-gc-root=true` option requests GC-root paths during the dump, which can pause the application; enable it only when investigating a specific memory leak and you understand the cost. Do not turn routine periodic checks into unbounded continuous file dumping.

## 5. `JFR.stop`: Stopping the Right Recording and Saving Final Data

Use `name` to pick the recording to end and `filename` to save the final artifact:

~~~bash
jcmd 12345 JFR.stop name=incident filename=/var/tmp/jfr/incident-final.jfr
~~~

Once it succeeds, the `incident` session stops recording. Other recordings (such as `baseline`) are **not stopped**. A stopped recording cannot be restarted as the same session; to continue collecting data, start a new recording via `JFR.start`.

The JDK 21 `jcmd` documentation explicitly states that **if `name` is omitted, no recording is stopped**. Likewise, `filename` specifies where to save data upon stopping; the docs warn that without a path, the recording's data may be discarded. Therefore, **whenever you need to preserve evidence, specify both `name` and `filename`**, even if you previously dumped a snapshot.

Example to avoid when you want to save final evidence:

~~~bash
jcmd 12345 JFR.stop name=incident
~~~

The command above still targets stopping `incident` without specifying an output file at stop time; do not expect a new artifact. `.jfr` files created by earlier `dump` calls remain separate artifacts and are not "undone" just because the recording stopped.

**Stopping a recording ≠ stopping the JVM.** `JFR.stop` manages an observation session; it does not terminate the Java process. Run `JFR.check` afterward to verify state rather than relying solely on a zero-error return.

## 6. Two-Recording Scenario: Baseline and Investigation

A sound pattern is to keep a low-detail background recording running while briefly running a `profile` recording. The scenario below targets **a single JVM** with PID 12345; all commands operate on that PID.

### Step A — Start two recordings with distinct names

~~~bash
jcmd 12345 JFR.start name=baseline settings=default disk=true maxage=1h maxsize=256m
jcmd 12345 JFR.start name=incident settings=profile disk=true maxage=15m maxsize=128m
~~~

- `name=baseline` and `name=incident` are identifiers used for subsequent management commands. Clear, unique names prevent picking the wrong one.
- `settings=default` is a balanced config for long monitoring; `profile` collects finer detail and may raise overhead and volume. Choose settings for the goal rather than leaving `profile` running indefinitely.
- `disk=true` allows writing recording data to disk; `maxage` and `maxsize` cap retained data so it does not grow unbounded. These are **retention** settings, not "auto-stop after one hour."
- If you want a recording to stop automatically after an interval, `JFR.start` provides `duration=...`; omit `duration` in workflows where you explicitly control `JFR.stop` in later steps.

### Step B — Verify both

~~~bash
jcmd 12345 JFR.check
jcmd 12345 JFR.check name=incident verbose=true
~~~

Expected logic: two active recordings, each with its own name/ID and configuration. JFR output is generated by the JVM at runtime, so IDs, timestamps, and sizes are **dynamic**—do not copy hardcoded numbers from an example.

### Step C — Export two independent snapshots by name

~~~bash
jcmd 12345 JFR.dump name=baseline maxage=5m filename=/var/tmp/jfr/baseline-5m.jfr
jcmd 12345 JFR.dump name=incident filename=/var/tmp/jfr/incident-snapshot.jfr
jcmd 12345 JFR.check
~~~

After dumping succeeds, **both recordings can remain RUNNING**. Distinct output filenames separate investigation targets. Do not omit `name` in `JFR.dump` if you only want `incident`.

### Step D — Stop only the investigation recording

~~~bash
jcmd 12345 JFR.stop name=incident filename=/var/tmp/jfr/incident-final.jfr
jcmd 12345 JFR.check
~~~

On the next check, `incident` has ended; `baseline` remains active. Both `incident-snapshot.jfr` and `incident-final.jfr` can exist, but they do **not mean two sessions**: they are two artifacts from the lifecycle of one recording.

### Step E — When baseline is truly no longer needed

~~~bash
jcmd 12345 JFR.dump name=baseline maxage=5m filename=/var/tmp/jfr/baseline-last5m.jfr
jcmd 12345 JFR.stop name=baseline filename=/var/tmp/jfr/baseline-final.jfr
jcmd 12345 JFR.check
~~~

This step is **optional depending on operational goals**; in many systems, the background recording stays running for future incidents. If both are stopped, `JFR.check` may report no remaining recordings.

### Important: Multiple recordings do not mean two isolated JVMs

Each recording has its own **name, lifecycle, settings, and dump scope**, yet all run **inside the same JVM** and share JFR's event-collection infrastructure. When recordings have different settings, an event enabled by one recording can affect available data or collection cost in the context of another. Do not assume a `settings=default` baseline guarantees the baseline file contains strictly only events listed in that profile while a `profile` recording runs alongside it. Verify actual file contents with `jfr summary`/`jfr print`.

## 7. Inspecting `.jfr` Files After `dump` and `stop`

On the host/volume where the JVM wrote the artifacts:

~~~bash
ls -lh /var/tmp/jfr/incident-snapshot.jfr
ls -lh /var/tmp/jfr/incident-final.jfr
jfr summary /var/tmp/jfr/incident-final.jfr
~~~

`jfr summary`, included with the JDK, reads `.jfr` statistics such as recording duration, event types, and event counts/sizes. If the tool cannot open the file, verify the path, permissions, file size, integrity, and parser version. Never declare success just because a filename exists if the file is empty or corrupt.

You can filter events by name:

~~~bash
jfr print --events jdk.CPULoad /var/tmp/jfr/incident-final.jfr
~~~

Note: data appears only if that event type was enabled, actually occurred, remained within retention, and was included in the exported artifact. An empty `jfr print` result **does not prove the JVM had no CPU activity**.

Beyond the CLI, you can open the artifact in **Java Mission Control (JMC)** to inspect timelines, threads, GC, CPU, or allocation events. When comparing two files, cross-check recording name/ID, time window, and settings; file size differences may reflect duration or event settings rather than workload.

**JFR is not an HPROF heap dump.** A `.jfr` file is a timeline of events, whereas `.hprof` is a snapshot of the heap object graph. `JFR.dump` and `GC.heap_dump` differ in data, runtime impact, and diagnostic purpose; they do not replace each other.

## 8. Java 17+ Example for Practicing with `jcmd`

The program below intentionally stays alive for about two minutes, emitting one **custom JFR event** per second so learners can attach to the process and practice managing two recordings. It is standalone code compiling on **JDK 17+ with the `jdk.jfr` module**.

Save the program as **`JfrRecordingLab.java`**:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

public class JfrRecordingLab {
    @Name("lab.WorkUnit")
    @Label("Work Unit")
    static class WorkUnit extends Event {
        @Label("Iteration")
        int iteration;
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());
        for (int i = 1; i <= 120; i++) {
            WorkUnit event = new WorkUnit();
            event.iteration = i;
            event.begin();
            Thread.sleep(1_000L);
            event.end();
            event.commit();

            if (i % 30 == 0) {
                System.out.println("Completed=" + i);
            }
        }
        System.out.println("Done");
    }
}
~~~

**Terminal A** — compile and run the program:

~~~bash
javac JfrRecordingLab.java
java JfrRecordingLab
~~~

Example lines printed by the program itself:

~~~text
PID=<actual PID of this run>
Completed=30
Completed=60
Completed=90
Completed=120
Done
~~~

The `PID=...` line contains an OS-assigned integer that changes on every run. The `Completed=...` lines appear every 30 iterations; if you stop the program early or the process is interrupted, some lines will not appear.

**Terminal B** — while the program is still running, replace `12345` with the printed PID. Use a writable directory:

~~~bash
jcmd 12345 JFR.start name=lab-baseline settings=default disk=true maxage=5m maxsize=64m
jcmd 12345 JFR.start name=lab-incident settings=profile disk=true maxage=5m maxsize=64m
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=lab-incident filename=/var/tmp/jfr/lab-incident.jfr
jcmd 12345 JFR.stop name=lab-incident filename=/var/tmp/jfr/lab-incident-final.jfr
jcmd 12345 JFR.check
jcmd 12345 JFR.stop name=lab-baseline filename=/var/tmp/jfr/lab-baseline-final.jfr
~~~

Run these commands **before the program prints `Done`**; once the program exits, the PID can no longer be attached to. To try again, restart Java and grab the new PID.

Then:

~~~bash
jfr summary /var/tmp/jfr/lab-incident-final.jfr
jfr print --events lab.WorkUnit /var/tmp/jfr/lab-incident-final.jfr
~~~

If the recording was active while `WorkUnit` committed and custom events were enabled, the file can contain events named `lab.WorkUnit` along with the `iteration` field. Event counts **depend on start/dump/stop timing**; there is no fixed numeric stdout from `jcmd` or `jfr`. Which configuration actually enabled the event can be checked via `JFR.check name=lab-incident verbose=true` and file metadata.

## 9. Very Common Operational Mistakes

| Symptom / Misconception | Possible Cause | Action |
| --- | --- | --- |
| `JFR.check` reports no recordings | Recording not started, already stopped, or querying wrong PID | Verify exact PID and start when permitted |
| After `JFR.dump`, `check` still shows the recording | **This is expected behavior**: dump does not stop | To stop it, call `JFR.stop name=...` |
| File contains unexpected events | Dumped without `name`, or multiple recordings changed collected events | Specify `name`; inspect `verbose=true`, file stats, and concurrent recordings |
| Older data missing from dump | Start-time `maxage`/`maxsize` evicted old data; dump was late | Increase retention for future captures, dump promptly; lost data cannot be recovered |
| `JFR.stop` stops no recording | Omitted `name` or wrong `name` | Run `JFR.check`, use exact `name` |
| Stopped but no final artifact found | Omitted `filename` or wrong filesystem | Use `JFR.stop name=... filename=/path/to/...jfr` and check on target JVM |
| `jcmd` attach error | Wrong PID, missing permissions, process exited, different PID namespace, or attach disabled | Verify host/user/PID/runtime; operate in the right namespace |
| File write fails | Directory missing, wrong permissions, disk/quota full, or filename collision | Create writable directory, pick new filename, monitor disk space |
| `JFR.dump` has less data than expected | Filter window, event settings, or recording just started | Check timestamps, `maxage`, `begin`, event types, and start time |
| JFR adds load | Heavy profile/events, too many recordings, or dumping too frequently | Bound duration/retention, monitor overhead, reduce detail level |
| Multiple sessions, only want to stop one | Confused recording name/ID, automation picked wrong session | Use unique names, check before and after stop, never stop by guessing |

Some commands have JVM-version-specific parameters; use `jcmd <PID> help JFR.dump` and variants of `JFR.check`/`JFR.stop` to confirm on your runtime. This guide references **HotSpot JDK 21**; other JVMs or JDKs may differ.

## 10. Practice Choosing Operations by Requirement

**Scenario A:** The service has a running `baseline`; you need an event file for the last 5 minutes and must keep monitoring. → `JFR.check` to confirm name, then **`JFR.dump name=baseline maxage=5m filename=...`**. Do not stop.

**Scenario B:** Both `baseline` and `incident` exist; investigation is done, you need to save the final `incident` result while `baseline` keeps running. → **`JFR.stop name=incident filename=...`**, then `JFR.check` to confirm `baseline` is still active.

**Scenario C:** An operator forgot the name and wants to export only `incident`. → **`JFR.check` first** to confirm the recording name. Never carelessly run `JFR.dump` without `name`, as that can export data from every recording.

**Scenario D:** You want to export data from one hour ago, but `baseline` was configured to keep only 10 minutes. → No dump command can recover data already evicted by retention; you must **design retention and capture timing before the incident recurs**.

**Pre-operation checklist:**
1. Have the **right PID, right JVM, right permissions**, and `help` confirming syntax.
2. Know the exact **recording name/ID**, state, and current settings via `JFR.check`.
3. For dumps, pick the exact **scope**, **time range**, **new file path**, and verify free disk space.
4. For stops, confirm which recording ends, **which final file to save**, and whether other recordings should stay running.
5. Afterward, **check status**, validate the file with `jfr summary`, protect it, and attach timestamp/PID/settings metadata to the evidence.

**Remember:** `JFR.check` = **inspect**, `JFR.dump` = **export snapshot and keep recording**, `JFR.stop` = **end the selected session**. In multi-recording environments, **`name` and pre/post checks** are the key to preserving the right data and lifecycle.

## References

- Oracle Java SE 21 — **The jcmd Command**, describing `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop` and options: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java SE 21 — **The jfr Command**, `jfr summary`, `jfr print`, `jfr view`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle Java SE 21 — **Recording API**, lifecycle of a recording: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Dev.java — **Getting Started with JDK Flight Recorder**: https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/getting-started/

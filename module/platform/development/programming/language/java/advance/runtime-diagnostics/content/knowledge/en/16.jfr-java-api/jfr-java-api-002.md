# 16.2 Recording Lifecycle: Creation, Configuration, Start, Stop, Dump, and Close

## Learning Objectives

`jdk.jfr.Recording` is the API for controlling a **Java Flight Recorder (JFR)** session from Java code: creating a recording, configuring events, starting, writing data to a `.jfr` file, stopping, and releasing resources. The key is not just knowing method names, but understanding **valid states and whether data is still retained or already released** after each call.

After this lesson, you will be able to:

1. Distinguish `NEW`, `DELAYED`, `RUNNING`, `STOPPED`, and `CLOSED`, along with valid state transitions.
2. Choose constructors/configurations, enable events, and configure thresholds, storage, duration, and retention policies before `start()`.
3. Explain why `dump(Path)` does not stop a recording, why `stop()` does not implicitly create a file, and why `close()` does not replace saving.
4. Choose properly between two workflows: **manual dump after stop** and **`setDestination` automatic write on stop**.
5. Write, compile, and run a Java 17+ program demonstrating the full `NEW → RUNNING → STOPPED → CLOSED` sequence; read back the recorded events.
6. Handle exception flows, auto-stopping recordings, disk/memory retention, and missing JFR data.

Examples use the `jdk.jfr` API on HotSpot/OpenJDK Java 17+; the runnable Java code below was verified on OpenJDK 24. The `RecordingStream` API is for near-real-time event consumption and has its own lifecycle; this lesson covers only `Recording`.

## 1. Distinguishing the Recording Object, Collection Session, and JFR File

A `Recording` is an application-side handle: it has an ID, name, event configuration, retention policy, and `RecordingState`. The **active collection session** is the period during which events are actually received; a `.jfr` file is an extracted snapshot of data retained by the recording. These three entities have related yet distinct lifecycles.

| API | Meaning | What must not be assumed |
| --- | --- | --- |
| `new Recording(...)` | Creates a handle, initial state `NEW` | Not collecting events yet; no destination file yet |
| `start()` | Starts event collection per settings, state `RUNNING` | Does not automatically export a `.jfr` file |
| `dump(path)` | Copies currently available data to a file | **Does not stop** a `RUNNING` recording |
| `stop()` | Ends the collection window; recording cannot be restarted | Does not necessarily produce a file |
| `setDestination(path)` | Sets the file to write automatically **on stop** | Calling this does not write the file yet; a successful stop may **auto-close** |
| `close()` | Releases data/resources bound to the handle | Not a dump/export command |

The easiest mistake is equating `stop()` with `close()`: without a destination set, a **STOPPED** recording still retains data for a later `dump()` when `toDisk=true`; **CLOSED** means data held by the handle has been released. If you call close before dump, the chance to export a file from that handle is lost.

## 2. State Machine of Recording

```text
               new Recording(...)
                       |
                       v
                      NEW
                       |
             +---------+------------------+
             |                            |
           start()                scheduleStart(delay)
             |                            |
             v                            v
           RUNNING                     DELAYED
             |                            |
             |                       delay expires
             |                            |
             |<---------------------------+
             |
             +---- dump(path) ----> RUNNING (does not stop)
             |
             +---- stop() --------> STOPPED
                                       |
                                       +-- dump(path), if toDisk=true
                                       |
                                       +-- close() --> CLOSED

  close() can terminate any still-open handle.
  When setDestination(path) is set and stop writes the file successfully,
  the recording closes automatically rather than staying open for manual dump.
```

| State | Origin | What can be done? |
| --- | --- | --- |
| `NEW` | Newly created | Set settings, `start()` or `scheduleStart()` |
| `DELAYED` | After `scheduleStart(delay)` | Wait for start time; do not assume events are already being collected |
| `RUNNING` | Successful `start()` or delay elapsed | Collect events; `dump(path)` to take a snapshot while continuing; `stop()` to end |
| `STOPPED` | Successful `stop()`, or recording auto-stopped due to duration | Cannot `start()` again; can dump if `toDisk=true` and not closed |
| `CLOSED` | `close()` or stop with destination written successfully | Cannot reuse handle to dump/start |

**Rules to remember:**

- A recording is a **one-shot** session. Once stopped, to start another measurement run, create a new `Recording`; do not call `start()` a second time.
- Calling `start()` on an already started/CLOSED recording or `stop()` when not started/already stopped are invalid state transitions that can throw `IllegalStateException`.
- According to the Javadoc, `dump(Path)` succeeds only when the recording is **RUNNING**, or when it is **STOPPED and toDisk=true**. In NEW/DELAYED/CLOSED, or STOPPED without a disk repository, it may throw `IOException`.
- `getState()` reflects the state observed at the moment of the call. If multiple threads control the same recording, checking state and acting still requires clear ownership/synchronization to avoid races.
- `scheduleStart(Duration)` creates a DELAYED phase; `setDuration(Duration)` can cause the recording to auto-stop after the configured time. Do not always assume a recording is still RUNNING in a cleanup callback.
- If `setDestination(path)` is set, `stop()` writes data to the file and **automatically closes the recording after a successful copy**. Do not try to dump again on the closed handle.

## 3. Creating a Recording Properly

### 3.1. Constructors and templates

Three common creation patterns:

```java
// Illustrative lines inside a method, omitting imports and exception handling:
Recording r1 = new Recording();
Recording r2 = new Recording(Configuration.getConfiguration("default"));
Recording r3 = new Recording(Configuration.getConfiguration("profile"));
```

These are **illustrative snippets**, not standalone programs. `Recording` and `Configuration` belong to `jdk.jfr`; every handle must be closed when finished.

- `new Recording()` creates a recording **without built-in event settings**. Do not assume it is equivalent to the `default.jfc` template.
- `Configuration.getConfiguration("default")` loads the JDK default configuration, useful for continuous collection with relatively low overhead.
- `Configuration.getConfiguration("profile")` loads a template for deeper analysis, which can generate more data and higher overhead. Neither template enables all events; verify the JDK version and actual settings.
- `new Recording(Map<String,String>)` accepts application-built settings; `setSettings(map)` **replaces** the current settings. `getSettings()` returns a map for inspecting/adjusting a copy; mutating that map does not update the recording unless you call `setSettings`.

**Finish configuration before `start()`**: The Javadoc recommends this so events and options apply consistently, avoiding mid-session changes that make measurements hard to compare.

### 3.2. Selecting events and settings

Example of the event API:

```java
// Snippet inside a method, assuming recording variable and MyEvent class already exist:
recording.enable(MyEvent.class).withThreshold(Duration.ZERO);
recording.enable("jdk.JavaMonitorEnter")
         .withThreshold(Duration.ofMillis(10))
         .withStackTrace();
recording.disable("jdk.ExceptionThrow");
```

This is **non-standalone illustrative code**: it requires a `MyEvent extends jdk.jfr.Event` class, `Duration`, and a valid `Recording`.

Common options:

- **enabled:** whether the event type is allowed to be collected by the recording.
- **threshold:** for events with duration, events shorter than the threshold are not saved. `Duration.ZERO` can be used in a narrow measurement window to see very short events as well.
- **stackTrace:** captures the event's stack trace, incurring additional overhead.
- **period:** some events are emitted periodically; sample counts do not equal the number of times a method ran.

Enabling an event does not guarantee it will appear: the workload must actually emit the event, the event must pass the threshold, the recording must be RUNNING, and the data must still be retained until dump time.

### 3.3. Recording-level options

| Method | Role | Operational notes |
| --- | --- | --- |
| `setName(String)` | Sets a human-readable name for the recording | `getId()` provides a distinct ID; do not rely solely on name when multiple recordings exist |
| `setToDisk(true)` | Enables JFR to use the disk repository; default `true` | The right choice when you need to dump after stop |
| `setToDisk(false)` | Does not continuously flush to the disk repository; bounded by in-memory buffers | `getSize()` returns 0 per API; no valid dump path after stop |
| `setMaxAge(Duration)` | Limits age of data retained in the repository | Old chunks are evicted and cannot be recovered by a later dump |
| `setMaxSize(long)` | Limits amount of retained data (bytes); `0` means unlimited | Old data may be evicted if the limit is exceeded |
| `setDuration(Duration)` | Auto-stops after the specified duration | Set before start, then check state before post-collection operations |
| `scheduleStart(Duration)` | Starts after a wait interval | Initial state is DELAYED; nothing collected before actual start |
| `setDestination(Path)` | Specifies the output file on stop | A successful write auto-closes the recording |
| `setDumpOnExit(true)` | Requests a dump when the JVM exits via supported JFR hooks | Cannot guarantee complete data on hard kill/crash |

Note that `setToDisk(true)` refers to **JFR's internal disk repository**, which does not mean a final report file exists at your desired path. The final output file must come from `dump(path)` or `setDestination(path)` on stop.

For long-running applications, without max age/max size limits, repository data can grow sharply; choose retention based on cost and the incident window you need to analyze.

## 4. Two Valid Operation Sequences

### 4.1. Sequence A: manual dump control

When you need a snapshot while running and a final file after finishing:

```text
create & configure (toDisk=true, no setDestination)
        |
      start
        |
   run workload A
        |
 dump(snapshot.jfr)  -- still RUNNING
        |
   run workload B
        |
      stop            -- STOPPED
        |
  dump(final.jfr)     -- valid because toDisk=true
        |
      close           -- CLOSED
```

`dump(Path)` in RUNNING does not stop the recording. The snapshot contains only data available **up to the time of the dump**, and does not automatically update with subsequent events. `stop()` ends collection, and `dump(finalPath)` on STOPPED can export the final file if the recording used the disk repository and still holds data.

### 4.2. Sequence B: automatic file write on stop

When you only need one final file:

```java
// Pattern inside a method; doWork() is an application method you must define.
Path output = Path.of("final.jfr");
try (Recording r =
        new Recording(Configuration.getConfiguration("default"))) {
    r.setName("one-shot");
    r.setDestination(output);
    r.start();
    doWork();
    r.stop(); // Automatically writes final.jfr and closes recording on success.
}
```

This is an **illustrative** snippet, not standalone because `doWork()` is undefined. `setDestination` only registers the output location. Data is written on stop; after a successful write, the recording has already auto-closed, so **do not call `r.dump(...)` afterward**.

If you plan to use `setDuration` for auto-stop, setting a destination ensures the file is exported when it auto-stops (provided the process completes normally). When you need to verify save errors or timestamps, check that the actual file exists and is readable rather than assuming.

### 4.3. How does Stop differ from Close?

In Sequence A, `stop()` halts creation of new data while keeping content for a subsequent dump; `close()` releases the retained content. The sequence **stop → close → dump** is invalid. Follow **stop → dump → close**.

In Sequence B, a successful stop **already includes file export and close** because a destination was configured. A subsequent dump call on that recording will fail. If you want an additional snapshot file, dump **before** stop while still RUNNING, or use Sequence A.

## 5. Runnable Java 17+ Program with Verified Stdout

This example creates a custom `demo.Milestone` event so it does not depend on random GC/I/O occurrences. The program emits two events, dumps a snapshot while RUNNING, stops, dumps the final file, counts the events, and closes via `try-with-resources`.

```java
// File: RecordingLifecycleDemo.java
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

public class RecordingLifecycleDemo {
    @Name("demo.Milestone")
    static class Milestone extends Event {
        String step;
    }

    static void emit(String step) {
        Milestone event = new Milestone();
        event.step = step;
        event.commit();
    }

    static long countMilestones(Path path) throws Exception {
        try (RecordingFile reader = new RecordingFile(path)) {
            long count = 0;
            while (reader.hasMoreEvents()) {
                if ("demo.Milestone".equals(reader.readEvent().getEventType().getName())) {
                    count++;
                }
            }
            return count;
        }
    }

    public static void main(String[] args) throws Exception {
        Path snapshot = Files.createTempFile("jfr-running-", ".jfr");
        Path result = Files.createTempFile("jfr-final-", ".jfr");
        Recording recording = new Recording(Configuration.getConfiguration("default"));
        try {
            try (recording) {
                recording.setName("lifecycle-demo");
                recording.setToDisk(true);
                recording.enable(Milestone.class).withThreshold(Duration.ZERO);
                System.out.println("created=" + recording.getState());

                recording.start();
                System.out.println("started=" + recording.getState());
                emit("first");

                recording.dump(snapshot);
                System.out.println("after-running-dump=" + recording.getState());
                emit("second");

                recording.stop();
                System.out.println("stopped=" + recording.getState());
                recording.dump(result);
                System.out.println("saved-events=" + countMilestones(result));
            }
            System.out.println("closed=" + recording.getState());
        } finally {
            Files.deleteIfExists(snapshot);
            Files.deleteIfExists(result);
        }
    }
}
```

Save the file with the exact name `RecordingLifecycleDemo.java`. Compile and run with JDK 17+:

```bash
javac RecordingLifecycleDemo.java
java RecordingLifecycleDemo
```

Exact stdout verified on OpenJDK 24:

```text
created=NEW
started=RUNNING
after-running-dump=RUNNING
stopped=STOPPED
saved-events=2
closed=CLOSED
```

Explanation:

1. `NEW`: handle exists, not collecting events yet.
2. `RUNNING` after start: recording receives enabled events. `emit("first")` commits the first event.
3. `after-running-dump=RUNNING`: `dump(snapshot)` exports a snapshot while the recording continues running; the `second` event is committed after the dump.
4. `STOPPED` after stop: recording accepts no new events, still retains data for dumping because `toDisk=true` and no destination was set.
5. `saved-events=2`: the final file contains both instances of `demo.Milestone`. `RecordingFile` iterates over event types and counts both events accurately.
6. `CLOSED` after exiting `try-with-resources`: the handle has been closed.

The snapshot and final files are created in the OS temp directory and deleted after the test. If you need to open the file in JDK Mission Control, intentionally save the diagnostic file to a persistent path and do not delete it before analysis. This example does not demonstrate disk errors, crashes, or write permissions; production code needs separate handling for those.

## 6. Stop, Dump, and Close in Exception Flows

`Recording` implements `AutoCloseable`/`Closeable`. `try-with-resources` guarantees `close()` runs when leaving scope, even if the workload throws an exception; **however, it does not guarantee that a file was dumped**.

Consider this illustrative snippet:

```java
// Illustrates logic inside a method; configuration, work, and destination are supplied by the application.
try (Recording r = new Recording(configuration)) {
    r.setToDisk(true);
    r.start();
    work();             // If this throws an exception, lines below are skipped.
    r.stop();
    r.dump(destination);
}
```

If `work()` throws an exception, the recording is closed on exiting the `try` block, **before stop/dump** in the normal path. Therefore, do not promise a file will exist when an error occurs. When the requirement is to preserve diagnostic evidence even if business logic fails, perform cleanup inside `finally` with state checks and dedicated error handling for exporting the file.

Mental model (pseudocode, **not literal runnable Java**):

```text
create + configure
try:
    start
    run workload
finally:
    if getState() == RUNNING:
        stop (if policy requires)
    if getState() == STOPPED and isToDisk():
        dump(result.jfr) if evidence is needed
    close even if dump/stop fails
```

Because `stop()`/`dump()` can throw exceptions, real code must preserve the original error, log additional cleanup errors, and always close. If a destination was set and stop auto-closed the handle, do not execute the dump branch on a CLOSED handle.

Two situations require extra care:

- **Duration/external auto-stop:** a `finally` callback must not call `stop()` again if the state is already STOPPED.
- **Multiple threads controlling the handle:** checking `getState()` then stopping does not prevent races; assign a single owner responsible for the lifecycle or use appropriate synchronization.

## 7. Files, Repository, and Data Completeness

The existence of a `.jfr` file **does not guarantee it contains all the events you expect**.

- The event was not enabled or did not meet the threshold.
- The event occurred **before start** or **after stop**.
- A snapshot was dumped while RUNNING **before** the target event occurred.
- `maxAge`/`maxSize` evicted older chunks from the disk repository.
- `toDisk=false` bounded data to memory buffers; `dump` after STOPPED is unavailable.
- Disk write failed, JVM exited abnormally, or dump file was corrupted.
- The viewer tool applied event type, time range, or thread filters.

Distinguish the destination file from the repository: `setToDisk(true)` allows JFR to flush into its internal repository; it does not choose `result.jfr` for you. You must call `dump(Path)` or `setDestination(Path)` + stop. `getSize()` reflects the size of recording data in the repository after flushing (per API docs), **not the exact size of the exported file**; when `toDisk=false`, this method returns 0, which does not mean no events exist in the buffer.

Once a real file is saved, inspect it using JDK tools:

```bash
jfr summary path/to/result.jfr
jfr metadata path/to/result.jfr
jfr print --events demo.Milestone path/to/result.jfr
```

`path/to/result.jfr` is only an example path. `jfr summary` shows the actual event counts in the file; `metadata` describes event schemas, not proof of instances; `print` lists instances matching the filter. Before concluding events are missing, check settings, timestamps, and whether the file holds sufficient history.

## 8. Error Scenarios and Fixes

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| `start()` throws `IllegalStateException` | Recording already started, STOPPED, or CLOSED | Create a new recording for a new measurement run |
| `stop()` throws `IllegalStateException` | Not started yet, already stopped, or duplicate shutdown handler call | Check state and assign a single owner |
| `dump()` throws `IOException` | NEW/DELAYED/CLOSED, STOPPED with `toDisk=false`, or unwritable path | Ensure valid state; use `toDisk=true` if dumping after stop; check filesystem |
| Stop finishes with no file | Neither `dump` called nor destination set | Pick one of the two export sequences in section 4 |
| Cannot dump again after stop | `setDestination` auto-closed the recording on successful write | Use the destination file; if an extra snapshot is needed, dump before stop |
| Expected events missing in file | Event disabled, threshold, wrong window, retention, or wrong event type | Check configuration and event counts; re-record if needed |
| File too large | Unbounded retention, verbose events, long duration | Set `maxAge`/`maxSize`/threshold; select only needed events |
| `getSize()==0` with `toDisk=false` | Not using disk repository | Do not conclude the recording has no events |
| Cleanup loses diagnostic data | `close()` before `dump()` | Dump before close; design the error path |
| Unreadable file after crash | Dump did not complete or data was not flushed | Check logs/actual file; do not treat dump-on-exit as crash-proof |

### Misconceptions to eliminate

**"Calling dump stops the recording."** No. `dump` while RUNNING creates a snapshot and the recording stays RUNNING. Proof is the example printing the exact state after a live dump.

**"Stop and close are equivalent."** No. With `toDisk=true` and no destination, STOPPED can still dump, while CLOSED cannot.

**"Once start is called, every event is present."** No. A recording only captures events that are configured, occur within the recording window, and pass filters.

**"Setting destination exports the file immediately."** No. The file is written on stop, and export success must still be verified.

**"STOPPED can always be dumped."** No. Javadoc requires `toDisk=true` for dumping after stop. `toDisk=false` suits buffer-only strategies and must be handled while RUNNING if a snapshot needs to be exported.

**"JFR using a disk repository means a final analysis file is automatically created."** No. The repository is not the same as the export file; specify an explicit output path.

**"Closing in finally is enough to save data on error."** No. Close releases data. You need an explicit stop/dump policy before close on both success and error paths.

## 9. Applying This in Real Applications

1. **Define the measurement goal:** CPU, lock contention, allocation, GC, I/O, or custom events? Choose `default`/`profile` and the required events/thresholds.
2. **Decide duration and window:** start immediately, schedule a delay, or set a duration? Estimate workload milestones.
3. **Choose a file strategy:** manual `dump` (especially if live snapshots are needed) or `setDestination` (one file on stop). Document storage location, retention, and disk budget.
4. **Create and configure Recording:** event settings, name, `toDisk`, `maxAge`, `maxSize`, duration/destination before start; log ID and timestamps as needed.
5. **Start and run workload:** check state when using auto-stop; avoid arbitrarily changing configuration mid-session.
6. **Dump/stop per chosen strategy:** verify each operation succeeds and avoid mixing the two workflows in a way that causes unexpected auto-close.
7. **Ensure close:** use try-with-resources/finally, handle exceptions, and avoid two places calling stop.
8. **Verify data:** confirm file exists and is readable; `jfr summary` shows expected time span and event types. Note limitations if events are missing.

### Handoff checklist

- [ ] Use a JDK supporting `jdk.jfr`; select the right template and event settings.
- [ ] Understand the current state; NEW, DELAYED, RUNNING, STOPPED, and CLOSED have distinct meanings.
- [ ] Set events, thresholds, storage, duration, and retention before start whenever possible.
- [ ] Do not restart a STOPPED recording; create a new handle.
- [ ] Live dump does not stop a recording; the snapshot file does not automatically receive future events.
- [ ] Use `toDisk=true` if you need to dump after stop.
- [ ] If using `setDestination`, a successful stop exports the file and auto-closes; do not dump again.
- [ ] Call close to release resources after saving the required data.
- [ ] Error paths must not lose evidence by closing before dumping.
- [ ] File has been read back with expected timestamps and events; do not draw conclusions from incomplete files.

**Core takeaway:** `start()` opens the recording window; `dump(Path)` takes a copy of the data and can happen while the recording is still RUNNING; `stop()` ends collection; `close()` releases data. Setting `setDestination(Path)` determines whether the recording **auto-exports and auto-closes** on stop. Design the exact lifecycle sequence to match your file needs, verify state, and inspect file contents before using JFR as diagnostic evidence.

## Official API Documentation

- Oracle JDK 21 — `Recording`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Oracle JDK 21 — `RecordingState`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/RecordingState.html
- Oracle JDK 21 — `Configuration`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Configuration.html
- Oracle JDK 21 — `EventSettings`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html
- Oracle JDK 21 — `RecordingFile`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html

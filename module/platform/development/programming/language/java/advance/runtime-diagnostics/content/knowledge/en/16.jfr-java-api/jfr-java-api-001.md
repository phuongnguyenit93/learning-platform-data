# 16.1 Controlling Recording and Configuration via the jdk.jfr API

## Learning Objectives and Scope

Java Flight Recorder (**JFR**) is the diagnostic event recording mechanism of the JVM and Java applications. Beyond controlling it via `jcmd` commands or startup flags, Java provides the standard **`jdk.jfr`** module so a program can **select configurations, start, stop, export, and manage recording lifecycles** directly within its own process.

After this lesson, you will be able to:

- Distinguish the roles of **`Configuration`**, **`Recording`**, **`EventSettings`**, and **`FlightRecorder`**; avoid confusing a `.jfc` configuration file with a `.jfr` recording file.
- Create a recording from the `default` preset, the `profile` preset, or a custom `.jfc` file, then tune a specific event.
- Correctly use `start()`, `scheduleStart()`, `stop()`, `dump()`, `setDestination()`, and `close()`; distinguish lifecycle states.
- Configure retention via `setToDisk()`, `setMaxAge()`, `setMaxSize()`, duration, and file location with awareness of overhead/limits.
- Write a Java 17+ program that self-records events, creates a `.jfr` file, reads back the results, and handles common errors.
- Integrate JFR into a diagnostic workflow with resource limits, access permissions, and verifiability.

**Technical scope:** Examples use APIs available since JDK 17 and are compiled with `javac --release 17`; a practical verification run used HotSpot JDK 24. Event parameters and presets may vary across JDK versions/implementations. JFR must be available in the JVM; `FlightRecorder.isAvailable()` indicates availability in the current process. Any conclusions about runtime or CPU cost must be measured under real workloads.

## 1. Architecture of Controlling JFR in Java

Key classes:

| API | Responsibility | When to use |
| --- | --- | --- |
| `jdk.jfr.Configuration` | Holds metadata and a map of event settings from a preset or `.jfc` file | Loading `default`, `profile`, or `custom.jfc` configurations |
| `jdk.jfr.Recording` | An object managing a single recording session; configure, start, stop, dump, close | Controlling a recording session via application logic |
| `jdk.jfr.EventSettings` | Adjusts settings for an event in a recording using a fluent API | `enable`, `withThreshold`, `withPeriod`, `withStackTrace` |
| `jdk.jfr.FlightRecorder` | JVM-level information/control, such as `isAvailable()`, list of event types, and recordings | Checking the JVM and introspection |
| `jdk.jfr.RecordingState` | Enum of `Recording` states | Ensuring valid method calls according to the lifecycle |
| `jdk.jfr.Event`, `@Name`, `@Label` | Defines an application-specific JFR event type | Recording business milestones/processing segments |
| `jdk.jfr.consumer.RecordingFile` | Reads recorded events from a `.jfr` file | Inspecting and analyzing after exporting the file |

A **configuration** is merely a description of event types and how to collect them. A **Recording** is a measurement session (running or not yet started) with its own ID, state, limits, and data. One `Configuration` can be used to create multiple `Recording` instances. A `.jfc` file is configuration XML, whereas a `.jfr` file is binary recording output and must be viewed with a supported tool.

Control flow diagram:

~~~text
Configuration.getConfiguration("default") / "profile"
                   or
            Configuration.create(pathToJfc)
                          |
                          v
                   new Recording(config)
                          |
             configure settings/retention
                          |
                       start()
                          |
                  JVM emits JFR events
                          |
           dump() while running (snapshot)
                          |
                       stop()
                          |
             dump() when STOPPED + toDisk
                          |
                       close()
                          |
               read .jfr file with JMC
                 or jfr / RecordingFile
~~~

You can use `jcmd <pid> JFR.start` externally or `new Recording(...)` from within the application; both control the JFR mechanism of the **same JVM**, though the Java `Recording` object's lifecycle is owned only by the application via the API. JFR is not a third-party library requiring a Maven dependency in a standard JDK that includes the `jdk.jfr` module.

## 2. Loading Configurations with `Configuration`

### 2.1 Selecting a built-in preset

~~~java
import jdk.jfr.Configuration;

Configuration lowOverhead = Configuration.getConfiguration("default");
Configuration profiling = Configuration.getConfiguration("profile");
~~~

These two statements are **code snippets inside a method** that handles or declares `throws Exception`; they are not a standalone Java program. `getConfiguration(String)` reads a preset by name and can throw `IOException` or `ParseException`. `default` is generally suitable for background recording with lower overhead; `profile` generally increases collected data for profiling within a bounded window. Do not infer with certainty which events are enabled solely from the preset name: verify against the actual JDK build.

You can list the presets provided by the JVM:

~~~java
for (Configuration c : Configuration.getConfigurations()) {
    System.out.println(c.getName() + " - " + c.getLabel());
}
~~~

This is also a **snippet** placed inside a Java method; the number and names of presets should not be hard-coded. Besides `getName()`, a `Configuration` provides `getLabel()`, `getDescription()`, `getProvider()`, `getContents()`, and `getSettings()` to inspect its origin and settings.

### 2.2 Reading a custom `.jfc` file

~~~java
import java.nio.file.Path;
import jdk.jfr.Configuration;

Configuration custom = Configuration.create(Path.of("custom.jfc"));
~~~

`Configuration.create(Path)` parses a JFR configuration file; it requires a valid path, read permissions, and well-formed XML content. If the file cannot be read or parsed, the program may receive `IOException` or `ParseException`; handle these so diagnostic tooling does not break business logic.

Do not directly edit `default.jfc` or `profile.jfc` inside the JDK. When modifications are needed, create a separate `custom.jfc` using JMC or the `jfr configure` tool, and store it alongside the application and tested JDK version.

### 2.3 `getSettings()` is a descriptor map, not a live control

Each setting has a key in the form:

~~~text
<event-name>#<setting-name> = <value>

jdk.JavaMonitorEnter#enabled = true
jdk.JavaMonitorEnter#threshold = 5 ms
jdk.ExecutionSample#period = 20 ms
~~~

These are syntax examples, not a claim that every event has every setting. The event level is a fully qualified name such as `jdk.JavaMonitorEnter`; the part after `#` is `enabled`, `threshold`, `stackTrace`, `period`, or another setting supported by that event type.

**Important pitfall:** Modifying the contents of `Configuration.getSettings()` **does not modify** the original `Configuration`; modifying `Recording.getSettings()` **does not automatically apply** changes to the recording. To create new settings, copy the map, update the values, and pass it to `new Recording(map)` or `recording.setSettings(map)`. `setSettings(...)` **replaces the entire** current set of settings; passing a map with only one key can discard other settings from the preset.

When modifying only a single event, the `Recording.enable(...)` and `EventSettings` APIs are usually clearer.

## 3. Three Ways to Create a `Recording` and Their Differences

~~~java
import java.util.Map;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

Recording empty = new Recording();              // No event settings from a preset yet.
Recording fromPreset = new Recording(
        Configuration.getConfiguration("default"));
Recording fromMap = new Recording(Map.of(
        "jdk.CPULoad#enabled", "true",
        "jdk.CPULoad#period", "1 s"));
~~~

This is an **illustrative snippet**; every `Recording` object must be managed and closed with `close()` after use, ideally via `try-with-resources`.

- `new Recording()` does not automatically come with a default settings bundle like `default.jfc`; choosing an explicit preset makes the collected data more predictable.
- `new Recording(Configuration)` initializes settings from a verifiable template.
- `new Recording(Map<String,String>)` lets you specify a settings map upfront; avoid omitting important events by making the map overly minimal.

A single JVM can have multiple recordings. Each recording has its own `getId()`, while `setName(...)` assigns a human-friendly name for operations/observation; the name is not a JVM-wide unique ID. Multiple recordings can record the same event type simultaneously, and JFR/instrumentation mechanisms still consume JVM resources; do not assume completely independent overhead across sessions.

## 4. Lifecycle of `Recording`: NEW → RUNNING → STOPPED → CLOSED

| State | Characteristics | Common actions |
| --- | --- | --- |
| `NEW` | Object created, collection not started yet | Choose settings, retention, name, path; `start()` |
| `DELAYED` | `scheduleStart(delay)` called, waiting for start time | Wait for JVM transition to RUNNING; avoid closing before scheduled start |
| `RUNNING` | Actively recording events according to recording settings | Check state/timestamp, `dump(path)` snapshot, or `stop()` |
| `STOPPED` | Recording stopped; this recording cannot be restarted | `dump(path)` if recorded to disk repository; `close()` |
| `CLOSED` | Data associated with the recording has been released | Cannot dump/restart; create a new recording if needed |

Common control pattern:

~~~java
try (Recording recording = new Recording(
        Configuration.getConfiguration("default"))) {
    recording.setName("payment-diagnostics");
    recording.start();
    // Execute the workload to measure.
    recording.stop();
    recording.dump(Path.of("payment-diagnostics.jfr"));
}
~~~

This example is a **snippet** using `Path`, `Recording`, and `Configuration` inside a method that handles exceptions; a complete standalone Java example is in section 7.

Behaviors to remember:

1. `start()` begins the recording from an appropriate state. Calling `start()` a second time on a stopped recording **cannot restart it**; create a new object for another session.
2. `scheduleStart(Duration.ofSeconds(10))` schedules the start after a delay. The object can be in `DELAYED`; if you call `close()` before it starts, the session will not capture the expected data.
3. `stop()` ends collection. If the recording has `setDestination(path)`, upon a successful stop JFR **writes the file and automatically closes** the recording; do not call `dump()` afterward.
4. `dump(path)` writes a snapshot to a file. It works **while RUNNING**, or when `STOPPED` if the recording wrote to the disk repository (`setToDisk(true)`). After `CLOSED`, the data has been released and cannot be dumped.
5. `close()` releases the recording's data and resources; if it has not been dumped or written via destination, the data may no longer be retrievable. `try-with-resources` ensures resource cleanup even when an exception occurs.

**Difference between `stop()` and `close()`:** `stop()` only ends recording (except when auto-closed due to destination); `close()` frees the recording's data. Do not close immediately after `stop()` without saving the file if you need to investigate later.

### 4.1 Two file export strategies: choose one explicitly

**A. Explicit export with `dump()`:** do not set a destination; after recording, call `stop()`, then `dump(...)`, then `close()`. This is the approach used in the runnable example. If the recording is RUNNING and you want a snapshot for investigation while continuing collection, you can call `dump(...)` without stopping.

**B. Automatic export on stop:**

~~~java
try (Recording recording = new Recording(
        Configuration.getConfiguration("default"))) {
    recording.setDestination(Path.of("automatic-at-stop.jfr"));
    recording.start();
    // Workload goes here.
    recording.stop();  // JFR writes to destination and automatically closes the recording.
}
~~~

This fragment is a snippet, not standalone. Do not mix the two approaches by calling `setDestination(...)`, then `stop()`, then `dump()`: when the destination is written successfully, the object is already `CLOSED`, so dumping after stop violates the lifecycle.

### 4.2 Measuring by duration and schedule

- `recording.setDuration(Duration.ofMinutes(1))` lets JFR automatically stop after the specified duration; you must keep the recording alive long enough. Calling `setDuration(...)` alone does not guarantee a saved file unless you configure a destination or dump in time.
- `recording.scheduleStart(Duration.ofSeconds(10))` schedules recording to start in the future; use when you want to measure a targeted window.
- `recording.getStartTime()`, `getStopTime()`, `getState()` provide lifecycle metadata; timestamps may be `null` before the corresponding event occurs.
- Do not sleep arbitrarily in a request-handling path just to wait for `setDuration`; for asynchronous recording, design clear ownership and coordinate stopping/closing with the application lifecycle.

## 5. Managing Repository, Retention, and Capacity

A `Recording` can write through a disk repository or be bounded to in-memory buffers:

| Method | Meaning | Precautions |
| --- | --- | --- |
| `setToDisk(true)` | Allows the JVM to flush recording data to the disk repository; this is also the default if unchanged | Requires sufficient disk space and retention controls |
| `setToDisk(false)` | Data is bounded by memory buffers, suited for short-term special cases | Older data may be lost; stopping and dumping behaves differently from to-disk mode |
| `setMaxAge(Duration)` | Retains only recent data within the specified time window in the disk repository | Expired chunks are discarded; older history is not guaranteed |
| `setMaxSize(long bytes)` | Limits retained size in the disk repository | When exceeded, the JVM discards old chunks; unit is **bytes** |
| `setDestination(Path)` | Writes to a file **on stop** and automatically closes on successful write | Path must be writable; do not dump again after auto-close |
| `setDumpOnExit(true)` | Requests a dump when the JVM exits | Not a replacement for file management, path setup, and handling abnormal exits |
| `getSize()` | Number of recording bytes flushed to the disk repository by the JVM so far | May be 0 for memory-only or unflushed recordings; not heap size |
| `dump(Path)` | Writes a snapshot to a file in a valid state | Involves I/O and requires a valid path; avoid concurrent requests writing to the same filename |

Practical retention configuration example:

~~~java
recording.setName("api-observation");
recording.setToDisk(true);
recording.setMaxAge(Duration.ofMinutes(5));
recording.setMaxSize(64L * 1024 * 1024);  // 64 MiB
~~~

This is a **snippet** applied to a recording before starting. With 5 minutes and 64 MiB, data can be evicted whenever **either limit** triggers cleanup of older chunks. A recording is not guaranteed to hold a full 5 minutes if the event rate is high.

`setDumpOnExit(true)` only applies under JVM exit conditions where the dump mechanism can execute; do not rely on it when a process is forcibly killed, OOM-killed, or crashes hard. Configure paths, verify permissions, and review sensitive data in events before automatically saving files to shared locations.

## 6. Tuning Events with `EventSettings` and `setSettings`

### 6.1 Enable/disable only the events you need to observe

~~~java
recording.enable("jdk.JavaMonitorEnter")
        .withThreshold(Duration.ofMillis(5))
        .withStackTrace();

recording.enable("jdk.CPULoad")
        .withPeriod(Duration.ofSeconds(1));

recording.disable("jdk.JavaExceptionThrow");
~~~

These are **snippets** assuming `Duration` and `recording` are already available. `enable(String)`/`disable(String)` take an event name; `enable(Class<? extends Event>)` takes an event class, which is useful when an event is loaded by multiple class loaders and you need to select the exact class. The `enable` method returns `EventSettings` for chaining calls.

Setting levels:

- **`enabled`**: collects or skips an event type. When running multiple recordings, JVM overhead may still be affected by other recordings that have that event enabled.
- **`withThreshold(Duration)` / `withoutThreshold()`**: used for events with an applicable duration/threshold. Lowering the threshold can sharply increase event volume and overhead.
- **`withPeriod(Duration)`**: used for events supporting periodic/sampling collection, such as `jdk.CPULoad`. Not applicable to every event.
- **`withStackTrace()` / `withoutStackTrace()`**: controls whether stack traces are requested for eligible events; increases diagnostic detail at a performance cost.
- **`with(String name, String value)`**: used when an event has a specific setting without a dedicated convenience method; the name and value must match the format accepted by the event.

Do not guess that every event supports `threshold`, `period`, or `stackTrace`. You can query the running JVM directly:

~~~java
import jdk.jfr.EventType;
import jdk.jfr.FlightRecorder;
import jdk.jfr.SettingDescriptor;

for (EventType type : FlightRecorder.getFlightRecorder().getEventTypes()) {
    if (type.getName().equals("jdk.JavaMonitorEnter")) {
        for (SettingDescriptor setting : type.getSettingDescriptors()) {
            System.out.println(setting.getName()
                    + " = " + setting.getDefaultValue());
        }
    }
}
~~~

This code belongs inside a method declaring exceptions if needed; it simply prints the setting descriptors of an event present on the current JVM. If the list is empty, check the event name, initialization/registration state, and implementation. Event names and settings can evolve across JDK versions.

### 6.2 Preserving a preset when overriding only a few keys

When you need to adjust multiple keys consistently, **copy the entire preset map** and modify it before creating the recording:

~~~java
import java.util.HashMap;
import java.util.Map;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

Configuration original = Configuration.getConfiguration("default");
Map<String, String> tuned = new HashMap<>(original.getSettings());
tuned.put("jdk.JavaMonitorEnter#enabled", "true");
tuned.put("jdk.JavaMonitorEnter#threshold", "5 ms");

try (Recording recording = new Recording(tuned)) {
    // Use the recording following the lifecycle in section 4.
}
~~~

This is a snippet and must be placed inside a method declaring `throws Exception` or catching exceptions. A full standalone Java example and verified stdout are in section 8. `new Recording(tuned)` receives all settings, including the unchanged default keys.

If a recording has already been created and you need to update the whole map:

~~~java
Map<String, String> merged = new HashMap<>(recording.getSettings());
merged.put("jdk.JavaMonitorEnter#threshold", "5 ms");
recording.setSettings(merged);
~~~

**Note:** `setSettings(merged)` replaces the recording's **entire** settings map. Do not pass just `Map.of("jdk.JavaMonitorEnter#threshold", "5 ms")` expecting the remaining default settings to stay intact. When adjusting a single event, `recording.enable(...).withThreshold(...)` is usually less error-prone.

### 6.3 Events with duplicate names across class loaders

`Recording.enable("my.app.WorkEvent")` applies to every event matching that name. A plugin-based application may load multiple classes with the same `@Name` across different class loaders; when you need to target a specific definition, use `enable(MyEvent.class)` or the event type ID from the current JVM's metadata. Do not carry event IDs across different runs or JVMs, as IDs are not stable between JVMs.

## 7. Complete Java 17+ Example: Configuration → Recording → `.jfr` File → Verification

This example generates 3 custom application events. It uses `default` by default, allows choosing `profile` or a custom file via CLI argument, writes the `.jfr` file, and reads it back with `RecordingFile`.

Save the file with the exact name **RecordingApiDemo.java**:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;

public final class RecordingApiDemo {
    @Name("training.WorkUnit")
    @Label("Work unit")
    @Category({"Training", "Diagnostics"})
    static final class WorkUnit extends Event {
        @Label("Task")
        String task;

        @Label("Items")
        int items;
    }

    public static void main(String[] args) throws Exception {
        if (!FlightRecorder.isAvailable()) {
            System.out.println("JFR_UNAVAILABLE");
            return;
        }

        String choice = args.length == 0 ? "default" : args[0];
        Configuration configuration = choice.endsWith(".jfc")
                ? Configuration.create(Path.of(choice))
                : Configuration.getConfiguration(choice);
        Path output = Path.of("programmatic.jfr");

        try (Recording recording = new Recording(configuration)) {
            recording.setName("learning-api");
            recording.setToDisk(true);
            recording.setMaxAge(Duration.ofMinutes(5));
            recording.setMaxSize(64L * 1024 * 1024);
            recording.enable(WorkUnit.class)
                    .withoutThreshold()
                    .withStackTrace();

            recording.start();
            for (int i = 1; i <= 3; i++) {
                WorkUnit event = new WorkUnit();
                event.task = "batch-" + i;
                event.items = i * 10;
                event.begin();
                Thread.sleep(12);
                event.end();
                if (event.shouldCommit()) {
                    event.commit();
                }
            }
            recording.stop();
            recording.dump(output);
            System.out.println("state=" + recording.getState());
        }

        long count = RecordingFile.readAllEvents(output).stream()
                .filter(e -> e.getEventType().getName()
                        .equals("training.WorkUnit"))
                .count();
        System.out.println("workEvents=" + count);
    }
}
~~~

Compile and run in a writable directory:

~~~sh
javac --release 17 RecordingApiDemo.java
java RecordingApiDemo
jfr summary programmatic.jfr
jfr print --events training.WorkUnit programmatic.jfr
~~~

**Stdout printed by the Java program itself** (when JFR is available and the file is created successfully):

~~~text
state=STOPPED
workEvents=3
~~~

In the file, three events are named `training.WorkUnit`, with `task` fields `batch-1`, `batch-2`, `batch-3` and `items` fields 10, 20, 30 respectively. Timestamps, durations, and stack traces depend on the runtime; do not hard-code those values. Each event uses `begin()` and `end()` to measure duration; `shouldCommit()` checks whether the event meets conditions and is enabled/above threshold at that moment; `commit()` actually sends the event to JFR.

The example was compiled with `javac --release 17` and run on HotSpot JDK 24. Both `java RecordingApiDemo default` and `java RecordingApiDemo profile` print the two lines above, and the `.jfr` file contains exactly 3 `training.WorkUnit` events. If JFR is unavailable, the `JFR_UNAVAILABLE` branch is another valid outcome; if write permission is missing or the preset/config file does not exist, the program throws an exception rather than printing the two success lines.

### 7.1 Why adjust only a specific event instead of building a new map?

`new Recording(configuration)` keeps the baseline settings from `default`/`profile`. `recording.enable(WorkUnit.class).withoutThreshold().withStackTrace()` adjusts only the application event type needed for the experiment. This avoids accidentally wiping out the preset's GC/CPU/thread events, which can happen when calling `setSettings` with an incomplete map.

### 7.2 Using the `profile` configuration or a custom `.jfc`

~~~sh
# Select the built-in profile:
java RecordingApiDemo profile

# Create a custom .jfc based on default, increasing contention detail:
jfr configure --input default.jfc --output custom.jfc 'jdk.JavaMonitorEnter#enabled=true' 'jdk.JavaMonitorEnter#threshold=5ms'

# Load the created file via Configuration.create(Path):
java RecordingApiDemo custom.jfc
~~~

Each run writes to the fixed `programmatic.jfr` path in the example. If you want to save multiple results for comparison, copy or rename the recorded file before the next run, or modify the program to use distinct output filenames. Loading `custom.jfc` requires the file to exist in the corresponding working directory; relative paths are not automatically synchronized between container and host.

The `jfr configure` command and custom file loading were verified on JDK 24. On other tools or JDK versions, check `jfr help configure`, the contents of `custom.jfc`, and the preset list before running.

### 7.3 Why is `RecordingFile.readAllEvents` only suitable for small demos?

This method loads all events from the file into Java memory; production files can be very large. When analyzing large recordings, use JMC, `jfr print` with filters, or open a `RecordingFile` and read sequentially via `hasMoreEvents()`/`readEvent()`, processing and closing the file. `RecordingFile` is a **consumer**, not a tool for controlling the lifecycle of an active `Recording`.

## 8. Second Complete Example: Tuning a Preset with a Map

The following example confirms that a copied map passed into `Recording` contains the expected settings without modifying the standard preset.

Save as **RecordingSettingsDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public final class RecordingSettingsDemo {
    public static void main(String[] args) throws Exception {
        Configuration original = Configuration.getConfiguration("default");
        Map<String, String> tuned = new HashMap<>(original.getSettings());
        tuned.put("jdk.JavaMonitorEnter#enabled", "true");
        tuned.put("jdk.JavaMonitorEnter#threshold", "5 ms");

        try (Recording recording = new Recording(tuned)) {
            System.out.println("name=" + original.getName());
            System.out.println("lockEnabled="
                    + recording.getSettings().get(
                            "jdk.JavaMonitorEnter#enabled"));
            System.out.println("lockThreshold="
                    + recording.getSettings().get(
                            "jdk.JavaMonitorEnter#threshold"));
        }
    }
}
~~~

Run:

~~~sh
javac --release 17 RecordingSettingsDemo.java
java RecordingSettingsDemo
~~~

Stdout (verified):

~~~text
name=default
lockEnabled=true
lockThreshold=5 ms
~~~

This second program **does not start the recording** and **does not create a `.jfr` file**, because its purpose is solely to verify configuration. Creating a `Recording` and reading its settings does not mean the JVM has recorded events. To actually collect data, you must call `start()`, generate a workload, `stop()`, and dump before `close()`.

## 9. Limitations to Know When Controlling via the API

### 9.1 Configurations can differ across recordings, but the JVM is a shared resource

Each recording has its own settings and retention. However, JFR operates inside a single JVM: CPU for event recording, buffers, disk I/O, instrumentation, and stack capture overhead still impact the workload. If recording A enables stack traces for a high-frequency event, recording B cannot "isolate" the application from A's overhead. Establish clear ownership, avoid opening multiple recordings with overlapping goals, synchronize names/timestamps, and close any recording no longer needed.

### 9.2 `Configuration` is not a data file and does not auto-start a recording

`Configuration.getConfiguration("default")` only reads settings. `new Recording(configuration)` only creates a `NEW` object. `recording.start()` is what actually enables collection. Even after calling `start()`, missing target events may mean the event never occurred, was disabled, had too high a threshold, the recording was too short, or the event source was not registered. Never treat a `.jfr` file without target events as proof that no bug exists.

### 9.3 Custom events and JVM events have different characteristics

Application-defined `Event` types can carry business fields and code-defined durations. `jdk.ExecutionSample` is sampling-based; `jdk.ObjectAllocationSample` is also sampling-based (with associated weights/semantics). `jdk.JavaMonitorEnter` records lock contention above a threshold; `jdk.GarbageCollection` records GC events. Counting these events cannot directly substitute for method invocation counts, total allocated bytes, or total CPU time. You must read the semantics of each event and its specific JDK settings.

### 9.4 Recording in code: permissions and sensitive data

Recordings can contain thread names, file paths, stack traces, system arguments/configurations, and custom application fields. Do not put tokens, passwords, personal payloads, or secrets into JFR event fields. Grant start/dump/read permissions only to trusted operators or mechanisms; avoid exposing an unrestricted endpoint allowing clients to specify arbitrary filesystem paths.

In production services, constrain duration, maxsize/maxage, storage directory, and access permissions, and log timestamps/PID/JDK/settings for each recording. Plan for old file cleanup and consider I/O impact; integrating via the API does not make recording "free" in performance terms.

### 9.5 Handling errors without breaking the business flow

Possible errors:

| Error / symptom | Possible cause | How to handle |
| --- | --- | --- |
| `FlightRecorder.isAvailable() == false` | JVM does not provide or has disabled JFR | Skip diagnostic feature and report the reason clearly |
| `IOException` or `ParseException` loading `Configuration` | Preset/ `.jfc` file missing, unreadable, or invalid XML | Check path/JDK; do not proceed with an assumed preset |
| `IllegalStateException` on invalid start/stop/dump | Recording already RUNNING/STOPPED/CLOSED or called in wrong state | Check `getState()` and design a single lifecycle owner |
| `IOException` during `dump` | Unwritable path, insufficient disk space, recording closed, invalid state | Choose a valid output path, ensure permissions/space, log error |
| File has few or no expected events | Event did not occur, high threshold, recording too short, event disabled | Inspect `getSettings()`, run representative workload, check `jfr summary` |
| File too large / latency spikes with JFR on | High event volume, heavy stack traces, unbounded retention | Shorten recording, tune events/thresholds, set `maxAge`/`maxSize` |
| `stop()` called but no file produced | Missing `dump(...)` or `setDestination(...)` | Dump when STOPPED + toDisk before close, or set destination before stop |
| `getSize() == 0` while app emits events | Recording is memory-only or buffers have not flushed to repository | Do not treat `getSize` as event count; check `isToDisk()`, dump, and inspect file |

In real applications, separate diagnostic failures from business failures: JFR recording is typically managed out-of-band and should not cause a primary request to fail just because a file could not be written. However, if "export recording" itself is an operator-initiated action, report the error explicitly; never silently claim a dump succeeded.

## 10. Comparing In-Code JFR Control with Other Approaches

| Approach | Advantages | Limitations and scope |
| --- | --- | --- |
| `-XX:StartFlightRecording=...` at process startup | Captures startup and infrastructure configuration outside code | Changing settings may require updating JVM flags and restarting |
| `jcmd <pid> JFR.start/check/dump/stop` | External control while JVM is running and attachable | Requires appropriate permissions/PID/namespace; operates outside the app |
| `jdk.jfr.Recording` | Integrates start/stop/export logic with application conditions | Requires managing lifecycle, retention, permissions, and I/O errors in code |
| `jdk.jfr.consumer.RecordingStream` | Processes events online via callbacks | A consumer/streaming API, not identical to the `Recording` file lifecycle |
| `jdk.jfr.consumer.RecordingFile` | Reads `.jfr` files after collection | Cannot be used to start/stop recordings |

A sensible business use case: after an internal monitor detects elevated latency, the program triggers **one** 60-second `Recording`, collects relevant lock/CPU events, saves a uniquely named file, and closes it. However, the API does not automatically know "when latency is abnormal": you must have reliable metrics and triggers, plus rate-limiting on triggers to prevent recording loops.

## 11. Controlled Deployment Scenario

If you want to integrate JFR into a high-throughput service, separate a **diagnostic controller/service** from the hot business handler. A straightforward design:

1. Initialize when requested by an authorized administrator or monitor; check `FlightRecorder.isAvailable()`.
2. Pick the appropriate `Configuration` and verify event settings on the current JVM.
3. Block duplicate requests or cap concurrent recordings; set name/ID, start time, duration, maxage/maxsize, and a writable directory.
4. Call `start()` and let the workload proceed; avoid blocking an HTTP request waiting on a long recording unnecessarily.
5. When a snapshot is needed, call `dump(path)` while RUNNING; when finished, call `stop()` then `dump(path)` if exporting manually, or use `setDestination` before stop for automatic export.
6. Call `close()` in `finally`/`try-with-resources`, save recording metadata (excluding sensitive data), and verify the file exists and is readable using `jfr summary` or JMC.
7. Clean up old files per retention policy; compare profiles against external baseline metrics (CPU, GC, latency, and workload) before drawing conclusions.

**Do not casually schedule `setDuration` and immediately close the object at the end of the method.** Asynchronous management must keep the `Recording` alive until recording and dumping finish. In the example code in section 7, the entire lifecycle is placed inside a synchronous `try-with-resources` block for clarity.

## 12. Thought Exercises and Answers

**Exercise A — distinguishing configuration and recording.** An application calls `Configuration.getConfiguration("profile")` and `new Recording(config)` without calling `start()`. Is JFR recording yet?

**Answer:** No. The object is in `NEW`; to record, you must call `start()` and generate events during the enabled window.

**Exercise B — lost recording data.** You call `start()` → `stop()` → `close()`, and only then call `dump(Path.of("x.jfr"))`. What happens?

**Answer:** Lifecycle error. `close()` frees the recording's data, so it can no longer be dumped. For a to-disk recording, dump after stop but **before close**, or set a destination to auto-write on stop.

**Exercise C — automatic export.** You called `setDestination(Path.of("x.jfr"))` before start, and later `stop()` succeeds. Do you still need to call `dump()`?

**Answer:** No. The destination is written on stop, and the recording closes automatically once copying succeeds. Calling dump afterward is an error.

**Exercise D — changing one setting.** Why is `recording.setSettings(Map.of("jdk.JavaMonitorEnter#threshold", "5 ms"))` more error-prone than `recording.enable("jdk.JavaMonitorEnter").withThreshold(Duration.ofMillis(5))`?

**Answer:** `setSettings` replaces the entire map; other preset settings may be lost. The fluent API modifies only the targeted event. If you must use `setSettings`, copy the original map and merge changes into it.

**Exercise E — file has no CPU samples.** `jdk.ExecutionSample` does not appear in an 80 ms recording. Does this prove there was no CPU work?

**Answer:** No. Sampling depends on enabled state, period, workload, and duration. Check settings, open a sufficiently long measurement window, and cross-check against actual CPU metrics.

**Exercise F — stable output.** In `RecordingApiDemo` from section 7, what does the line `workEvents=3` confirm?

**Answer:** Exactly three custom events named `training.WorkUnit` were read from the output file. It **does not** mean there were only three events in the entire recording, nor does it prove zero JFR overhead. Other JVM events may be present.

**Exercise G — long-term background recording.** Can you record indefinitely into the disk repository simply because `setToDisk(true)` is enabled?

**Answer:** You should not. Without size/age limits, the repository can grow; configure `setMaxSize` and `setMaxAge` according to your disk budget and diagnostic needs.

## 13. Operational Takeaways

- **`Configuration`** describes event settings; **`Recording`** owns a recording session and lifecycle; **`EventSettings`** tunes an event type; **`RecordingFile`** reads exported results.
- Basic lifecycle: **create → configure → start → workload → stop → dump → close**; snapshots can also be dumped while RUNNING.
- Choose **one** export strategy: explicit `dump`, or `setDestination` for automatic export on stop. Respect state transitions because STOPPED cannot restart and CLOSED retains no data.
- `getSettings()` is not a live handle for modifying settings; `setSettings` replaces the whole map, so merge completely or use `enable(...).with...`.
- Bound duration/size/age, protect file permissions and contents, and verify events were actually captured before analyzing.
- Even when controlled via the in-process API, **JFR is still a measurement tool with overhead**; use representative workloads and before/after results to draw sound conclusions.

### References

- Oracle Java 21 API, `Recording`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Oracle Java 21 API, `Configuration`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Configuration.html
- Oracle Java 21 API, `EventSettings`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html
- Oracle Java 21 API, `FlightRecorder`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/FlightRecorder.html
- Oracle Java 21 API, package `jdk.jfr` (event settings): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle Java 21 API, `RecordingFile`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html
- Oracle Java 21, `jfr` command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html

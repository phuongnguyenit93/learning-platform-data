# Tracking JFR Native Library Load/Unload Events

## 1. Objective and Context

A Java application can load machine code from operating system libraries via **JNI** (`System.load`/`System.loadLibrary`), the **Foreign Function & Memory API** (FFM, for example `SymbolLookup.libraryLookup`), a JVMTI agent, or other native execution paths. In systems with multiple modules, plugins, or class loaders, loading/unloading libraries at the wrong time can cause `UnsatisfiedLinkError`, make operating system dependencies difficult to identify, increase the number of resident libraries, or cause application errors when native resources have already been freed.

**Java Flight Recorder (JFR)** records events with timestamps, durations, and metadata for later analysis. For native libraries, it is necessary to distinguish between **events describing libraries currently present** and **events describing a load/unload operation occurring**. This is the most important point when reading a `.jfr` file.

After this lesson, you will be able to:

- Choose the right events by JDK version and distinguish snapshots from operation history.
- Start a recording before load/unload occurs, collect the `.jfr` file, and filter the necessary events.
- Read `name`, `success`, `errorMessage`, timestamp, duration, and stack trace when available.
- Use a Java + C example to trigger load/unload, then verify it with JFR.
- Investigate scenarios such as "library failed to load", "unload not seen", and "snapshot present but load event missing" without over-concluding from missing data.

## 2. Events and JDK Versions

| Event type | Availability | Used to answer |
| --- | --- | --- |
| `jdk.NativeLibrary` | Available on HotSpot JDK releases prior to JDK 22, including JDK 17/21, and continues on newer releases | *At the time JFR took the snapshot, which native modules were present in the JVM process?* |
| `jdk.NativeLibraryLoad` | Added since **JDK 22** in OpenJDK/HotSpot | *During the recording interval, which library load operations did the JVM perform, and did they succeed or fail?* |
| `jdk.NativeLibraryUnload` | Added since **JDK 22** in OpenJDK/HotSpot | *During the recording interval, which library unload operations did the JVM perform, and what was the outcome?* |

Full names (with the `jdk.` prefix) should be used when configuring or filtering events. Different JVMs/vendors for the same Java SE version may differ in event support; **check the event metadata of the actual running runtime** before deploying a monitoring workflow.

### `jdk.NativeLibrary` Snapshot

This is a **periodic event**: HotSpot lists the native modules currently loaded and emits corresponding records, typically per JFR chunk period (the common configuration is `everyChunk`). Important fields:

- `name`: native module name or path, depending on the operating system/loading mechanism.
- `baseAddress`: starting address of the module mapping.
- `topAddress`: ending address of the mapping, **which may be unknown/unavailable**.

A snapshot is **not** evidence that the library was just loaded at the exact timestamp of the record. Repeated appearance across multiple chunks also **does not mean** the library was reloaded multiple times.

### `jdk.NativeLibraryLoad` and `jdk.NativeLibraryUnload` Operation Events

These events belong to the runtime group and record information when the VM performs a load or unload. Fields of interest:

| Field | Interpretation |
| --- | --- |
| `name` | Name/path recorded for the library in the operation; may not be normalized identically across all platforms |
| `success` | `true` if the operation was recorded by the VM as successful; `false` if it failed |
| `errorMessage` | Error description if any; usually empty on successful operations |
| `startTime` | Event start time as measured by JFR |
| `duration` | Duration of the instrumented operation; does not default to the total initialization time of the entire application layer |
| `eventThread` | Thread associated with the event if the runtime can provide it |
| `stackTrace` | Stack trace when collected and this option is enabled |

In newer JDKs, the load event may also have additional fields regarding floating-point environment handling. **Do not hard-code every optional field** when writing multi-version analysis tools; use `jfr metadata` or `RecordedEvent.hasField(...)` before reading.

**Distinguish between "successful unload operation" and "module has disappeared from the memory map":** the JVM may invoke the unload mechanism, but the operating system, reference count, dependencies, or another native runtime still affect whether the file is actually unmapped. Cross-check with snapshots/OS when you want to conclude about memory residency status.

## 3. What Does JFR Observe and Not Observe?

Typical event flow:

```text
Java Application / JNI / FFM
        |
        | load/unload request
        v
JVM native loading mechanism
        |
        +--> NativeLibraryLoad / NativeLibraryUnload (JDK 22+)
        |        name, success, errorMessage, time...
        v
Operating system library loader
        |
        v
Native module in process address space
        |
        +--> NativeLibrary (snapshot of loaded modules)
```

Do not infer that this JFR mechanism is a tracker of **every** `dlopen`/`dlclose` or `LoadLibrary` operation from **all** code in the operating system. These are instrumented JVM events; operations performed directly by an arbitrary C library may not pass through that event-recording site. JFR also does not automatically report **who is holding every native handle** or prove that the library has freed all native heap.

A hypothetical timeline:

| 10:00:00 | 10:00:05 | 10:00:20 | 10:00:40 |
| --- | --- | --- | --- |
| JVM already loaded `libcore.so` | JFR started | `libaddon.so` is loaded | `libaddon.so` is unloaded |
| No load event in the new recording for `libcore.so` | Snapshot may list `libcore.so` | `NativeLibraryLoad(name=libaddon.so, success=true)` | `NativeLibraryUnload(name=libaddon.so, success=true)` |

If recording only starts at 10:00:05, **missing the load event for `libcore.so` is normal** and does not mean JFR is broken. Snapshots help identify libraries that were already present before recording started.

## 4. Checking Runtime Event Support

Use the same JDK/JVM as the process under investigation:

```bash
java -version

# Check the metadata that the current JDK's jfr command knows.
jfr metadata --events jdk.NativeLibrary

# Only expect these two events if the runtime supports them (HotSpot JDK 22+).
jfr metadata --events jdk.NativeLibraryLoad,jdk.NativeLibraryUnload
```

You can inspect event types using the Java API, such as the following expression (illustrative Java snippet, placed inside an appropriate method):

```java
jdk.jfr.FlightRecorder.getFlightRecorder()
        .getEventTypes()
        .stream()
        .map(jdk.jfr.EventType::getName)
        .filter(name -> name.startsWith("jdk.NativeLibrary"))
        .sorted()
        .forEach(System.out::println);
```

The list depends on **the running JVM**, so the output of this snippet must not be assumed to be identical between JDK 17 and JDK 22+. If JDK 17/21 lacks the two operation events, they cannot be "turned on" simply by editing `.jfc`; use the `jdk.NativeLibrary` snapshot or upgrade the JVM in an appropriate environment.

To see which fields actually exist in a recorded file, run:

```bash
jfr metadata --events jdk.NativeLibraryLoad,jdk.NativeLibraryUnload app.jfr
```

## 5. Recording and Viewing Events in a Running Application

This is the workflow for **HotSpot JDK 22+**. Replace `<PID>` with the actual PID, and ensure the `jcmd` tool can attach to the JVM and the target directory has write permissions.

### 5.1. Start Before Reproducing the Issue

```bash
# Find the JVM process.
jcmd -l

# Start recording. profile/default on HotSpot 22+ usually
# already enables NativeLibrary, NativeLibraryLoad, and NativeLibraryUnload.
jcmd <PID> JFR.start name=nativewatch settings=profile

# Confirm the recording exists and view the actual configuration.
jcmd <PID> JFR.check name=nativewatch verbose=true
```

After confirming the recording is **RUNNING** and the desired events are **enabled**, perform the application action that triggers library loading/unloading (for example, initializing a plugin or calling an API that has a native load step). If using a custom `.jfc` configuration or another JVM vendor, you must verify the events and `threshold`; set the threshold to `0 ms` for short operations if full capture is needed.

### 5.2. Dump, Stop, and Filter

```bash
# You can take a file snapshot while the recording is still running.
jcmd <PID> JFR.dump name=nativewatch filename=/tmp/nativewatch-sample.jfr

# Stop and write the complete recording.
jcmd <PID> JFR.stop name=nativewatch filename=/tmp/nativewatch-final.jfr

# Check which event types and counts are in the file.
jfr summary /tmp/nativewatch-final.jfr

# Load/unload operation events (JDK 22+).
jfr print --events jdk.NativeLibraryLoad,jdk.NativeLibraryUnload \
    --stack-depth 20 /tmp/nativewatch-final.jfr

# List of libraries at snapshot times.
jfr print --events jdk.NativeLibrary /tmp/nativewatch-final.jfr
```

The commands use Linux paths as examples; on Windows/macOS, choose valid paths. `JFR.dump` does not stop the recording; `JFR.stop` stops the specified recording. For short recordings, stop and dump after the operation to be measured has completed, and consider flush/chunk timing during analysis.

The `--events` filter accepts comma-separated names. `jfr print --json` can also be used to feed data into analysis scripts, though the JSON structure should be read according to the actual schema of the JDK in use.

### 5.3. Capturing from JVM Startup

If the issue occurs before you can attach, enable recording right at JVM startup:

```bash
java -XX:StartFlightRecording=filename=startup-native.jfr,settings=profile,dumponexit=true \
     -cp app.jar com.example.Main
```

This is a **command template** for an application with class `com.example.Main` in `app.jar`; replace it with the actual entrypoint. For an executable JAR with an appropriate manifest, use `-jar app.jar` instead of `-cp ... com.example.Main`.

Even a startup recording may miss very early operations during VM bootstrap; the absence of a stack trace or missing events is not enough to conclude with certainty that no native loading occurred. When you need to inspect the entire startup/OS loader phase, combine with appropriate operating system tools.

## 6. Hands-On: Triggering Load and Unload to Capture JFR

This example **runs standalone on Linux, HotSpot JDK 22+, and a C compiler**. It uses the FFM API standardized in JDK 22 to control lifecycle: `SymbolLookup.libraryLookup(path, arena)` loads the library when the lookup is created, and closing the arena requests unloading the library associated with it. This makes the unload scenario easier to reproduce than waiting for the garbage collector to collect a class loader containing a JNI library.

### 6.1. File `jfrprobe.c`

```c
/* No Java native method or JNI header is needed in this FFM example. */
int native_answer(void) {
    return 42;
}
```

### 6.2. File `NativeLibraryEventsDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.SymbolLookup;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Recording;

public final class NativeLibraryEventsDemo {
    public static void main(String[] args) throws Exception {
        Path library = Path.of("libjfrprobe.so")
                .toAbsolutePath()
                .normalize();
        Path output = Path.of("native-events.jfr");

        try (Recording recording = new Recording()) {
            recording.enable("jdk.NativeLibraryLoad")
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();
            recording.enable("jdk.NativeLibraryUnload")
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();
            recording.enable("jdk.NativeLibrary");
            recording.start();

            try (Arena arena = Arena.ofConfined()) {
                // The native library load operation occurs here.
                SymbolLookup symbols =
                        SymbolLookup.libraryLookup(library, arena);

                // Ensure the library actually has the exported symbol.
                if (symbols.find("native_answer").isEmpty()) {
                    throw new IllegalStateException(
                            "Missing native_answer symbol");
                }
            } // Close arena: request unloading the library associated with the lookup.

            recording.stop();
            recording.dump(output);
        }

        System.out.println("Recording saved: native-events.jfr");
    }
}
```

### 6.3. Compile and Run

```bash
# Linux, GCC/Clang, or compatible cc; the library must have the
# CPU architecture matching the JVM (e.g., both x86_64).
cc -std=c11 -fPIC -shared -o libjfrprobe.so jfrprobe.c

# Use JDK 22 or later for both javac and java.
javac NativeLibraryEventsDemo.java
java --enable-native-access=ALL-UNNAMED NativeLibraryEventsDemo

jfr print --events jdk.NativeLibraryLoad,jdk.NativeLibraryUnload \
    native-events.jfr
```

**Stdout of the Java program when run successfully:**

```text
Recording saved: native-events.jfr
```

The output from `jfr print` **does not have a fixed string**: timestamp, path, thread, stack, and duration vary by JVM, environment, and recording schedule. On a HotSpot build with full events, look for the record whose `name` contains `libjfrprobe.so` and check `success=true` for the load operation; when the arena closes, check the corresponding unload event. If the operating system keeps the library due to another dependency/reference, distinguish the unload request/event from actually unmapping from the process.

**Why is this example valid from Java 22, not Java 17?** The two operation events and the stable FFM used here are for JDK 22+. On JDK 21, FFM was still in preview and required corresponding configuration; JDK 17 does not have the stable FFM API with the imports above. For JDK 17/21, use the `jdk.NativeLibrary` snapshot workflow from the previous sections.

**New version note:** starting in JDK 24, `System.load`/`System.loadLibrary` and certain JNI/FFM operations enforce native access rules; `--enable-native-access=ALL-UNNAMED` for classpath code avoids warnings or denial mode when an operation is considered restricted. In modular applications, grant permission to the specific module rather than the entire classpath.

## 7. Analyzing with the Java API Instead of Only Reading Text

With the newly created `native-events.jfr` file, we can use `jdk.jfr.consumer.RecordingFile` to iterate through events and classify them by name. The following example is a **standalone program**; use a runtime capable of reading the recorded JFR file format, ideally the same JDK version.

### File `PrintNativeLibraryEvents.java`

```java
import java.nio.file.Path;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class PrintNativeLibraryEvents {
    public static void main(String[] args) throws Exception {
        Path input = Path.of(args.length == 0
                ? "native-events.jfr" : args[0]);

        try (RecordingFile recording = new RecordingFile(input)) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();
                String type = event.getEventType().getName();

                if (!type.equals("jdk.NativeLibraryLoad")
                        && !type.equals("jdk.NativeLibraryUnload")
                        && !type.equals("jdk.NativeLibrary")) {
                    continue;
                }

                String name = event.getString("name");
                System.out.println(type + " | " + name);

                // Snapshots do not have success/errorMessage.
                if (!type.equals("jdk.NativeLibrary")) {
                    boolean success = event.getBoolean("success");
                    System.out.println("  success=" + success);

                    if (!success && event.hasField("errorMessage")) {
                        System.out.println("  error="
                                + event.getString("errorMessage"));
                    }
                }
            }
        }
    }
}
```

Run:

```bash
javac PrintNativeLibraryEvents.java
java PrintNativeLibraryEvents native-events.jfr
```

The reader's stdout depends on the actual events, so **the number of lines or path order cannot be asserted in advance**. This is a Java 17+ program in terms of syntax and consumer API; JFR files created on newer JDKs may require a matching reader runtime.

When extending to a real analysis program, also retrieve `event.getStartTime()`, `event.getDuration()`, thread if available, and stack trace if non-`null`. For optional fields, check metadata/`hasField`. Do not assume every event has a stack trace; for example, events during VM bootstrap or special thread states may not carry a full stack.

## 8. Investigating Real-World Scenarios

### Case A — `UnsatisfiedLinkError` When Calling `System.loadLibrary`

**Symptom:** Java reports that `foo` cannot be loaded or a dependent library is missing.

1. Start JFR **before** the failing call; filter `jdk.NativeLibraryLoad` by `foo` or the related path.
2. Check `success=false` and `errorMessage` (if present), while also reading the Java exception.
3. Compare library architecture (32/64-bit, CPU architecture), file location, access permissions, ABI/JNI version, and transitive dependencies.
4. On Linux, you can use `ldd`/`readelf` on trusted files to inspect linkage; on macOS use `otool -L`, and on Windows use an appropriate tool to inspect PE/DLL dependencies.
5. Fix the name/path/dependency, then **create a new recording** and verify `success=true`.

An `errorMessage` indicates an error in the load path observed by the VM; it **does not** necessarily distinguish every logic error occurring inside `JNI_OnLoad` or after the library is successfully loaded.

### Case B — Unload Event Not Seen

The absence of an unload event may be due to:

- JFR started too late, stopped too early, or `jdk.NativeLibraryUnload` was not enabled.
- The library still has an owner: the JNI class loader is still reachable, the FFM arena has not been closed, or other code still holds a native handle.
- The JVM did not perform the unload operation through the code path JFR is tracking.
- The operating system's native state still retains the module due to dependencies/reference count.
- The JVM/vendor/version does not support the corresponding event.

For example, `System.loadLibrary("foo")` typically associates the native library with the calling class's class loader. There is **no** Java API to call a corresponding `System.unloadLibrary`. When the class loader becomes eligible for collection, the JVM may unload the library according to the associated lifecycle, but GC and unload timing **are not guaranteed by an application-chosen deadline**. Calling `System.gc()` is not a deterministic unload test.

### Case C — Library Seen in Snapshot but No Load Event

If `jdk.NativeLibrary` lists `libfoo.so` while `jdk.NativeLibraryLoad` does not record it, possibilities include:

- The library was already loaded before the recording started.
- The load event was disabled, filtered, or the operation did not go through the recorded hook.
- The runtime only supports snapshots, such as HotSpot JDK 17/21.
- The file does not contain the entire observation window (the recording was truncated by retention/dump settings).

**Do not conclude** that there is a leak solely from this discrepancy. A snapshot describes *existence*; a load event describes *change* within the recorded interval.

### Case D — Multiple Loads/Unloads with the Same Name

Build a timeline by `startTime` and `name`, then inspect `success`, `duration`, thread, and stack trace. Check whether creating/destroying class loaders/plugins or FFM arenas per request is causing the library to be loaded repeatedly. However, relying solely on the file name is not enough to assert that every event represents a distinct memory mapping; caching, alias paths, reference counting, and OS loader implementation all have an effect.

If load duration increases, measure initialization and dependency operations as well; the `duration` of the native load event is only the interval measured by the JFR hook and **does not by itself prove that the entire Java module or JNI initialization time is the cause of slowness**.

## 9. Practical Checklist When Capturing Native Library JFR

1. **Version:** confirm the JDK/JVM vendor; whether `jfr metadata` includes `NativeLibraryLoad`, `NativeLibraryUnload`, or only `NativeLibrary`.
2. **Time scope:** start the recording before the step that triggers the issue; for startup errors, use `-XX:StartFlightRecording` when appropriate.
3. **Configuration:** check `enabled`, `threshold`, and `stackTrace` via `JFR.check verbose=true` or metadata/config.
4. **File collection:** keep the recording stopped/dumped at the right time, and record the PID, JVM version, and reproduction steps for reference.
5. **Analysis:** separate snapshots from operations; examine `name` + `success` + `errorMessage` + timing, then thread/stack if available.
6. **Verification:** use Java exception details, class loader/arena lifecycle, and OS loader/dependencies to test hypotheses rather than concluding from a single event.
7. **Protect diagnostic data:** `.jfr` files can contain library paths, thread names, stack traces, and internal runtime information; restrict sharing to the necessary scope.

**Technical conclusion:** starting from JDK 22, `jdk.NativeLibraryLoad`/`jdk.NativeLibraryUnload` report native load/unload operations recorded by the JVM, while `jdk.NativeLibrary` provides a snapshot of libraries currently present. Combining both event types, recording at the right time, and cross-referencing the JNI/FFM lifecycle provides a more grounded diagnosis than looking only at `UnsatisfiedLinkError` or a list of `.so`/`.dll` files.

## References

- Oracle JDK 22, [`jfr` command](https://docs.oracle.com/en/java/javase/22/docs/specs/man/jfr.html) and [`jcmd` command](https://docs.oracle.com/en/java/javase/22/docs/specs/man/jcmd.html).
- Oracle JDK 22, [`SymbolLookup.libraryLookup` and `Arena` lifecycle](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- OpenJDK, [default JFR configuration (default.jfc)](https://github.com/openjdk/jdk/blob/master/src/jdk.jfr/share/conf/jfr/default.jfc) to inspect the defaults of each source version.
- Oracle JDK 24, [migration guide regarding native access](https://docs.oracle.com/en/java/javase/24/migrate/migrating-jdk-8-later-jdk-releases.html).

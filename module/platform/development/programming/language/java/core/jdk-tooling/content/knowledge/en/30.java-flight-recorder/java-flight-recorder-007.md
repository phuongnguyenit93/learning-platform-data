# JFR Dump Files in Java Flight Recorder

**Java Flight Recorder (JFR)** is a system for recording JVM and Java application events along a timeline. A **JFR dump file** is a recording file with the `.jfr` extension that contains events collected over a period of time. This file can be used to analyze CPU, garbage collection, allocation, threads, lock contention, class loading, I/O, and custom application-defined events.

A JFR dump is typically created when investigating an incident that has occurred or saving data for later analysis. A `.jfr` file is binary data, not plain text; use the `jfr` command or Java Mission Control (JMC) to read and analyze it.

## 1. What is a JFR dump file?

A JFR recording collects structured events. Each event may contain:

- The timestamp when it occurred and its duration if the event measures an operation over time.
- The event type and its specific data fields.
- The thread that emitted the event.
- The stack trace at the point where the event was recorded, if enabled in the configuration.
- Metadata describing the event, fields, data types, and category.

For example, a recording can store events for garbage collection, CPU load, object allocation, thread park, monitor contention, file I/O, socket I/O, exceptions, and custom events created by the application.

A `.jfr` file typically contains metadata and one or more data chunks. A chunk is the internal data unit of a recording; JFR tools use them to read, summarize, filter, or assemble recordings. Do not edit the file with a text editor or manually modify bytes in the file.

## 2. Distinguishing between a recording, a dump file, and a heap dump

Three concepts are often confused:

| Concept | Contents | When to use |
|---|---|---|
| JFR recording | The ongoing process of the JVM collecting events. | Monitoring the JVM over a period of time. |
| JFR dump file (`.jfr`) | The recorded events written to a file for storage and analysis. | Investigating performance, GC, threads, allocation, and runtime events. |
| Heap dump (`.hprof`) | A snapshot of the object graph in the heap at a single point in time. | Finding retained objects, retained size, and causes of memory leaks. |

JFR is not a heap dump. A recording may contain information about allocations and object sampling, but it is not a complete copy of every object currently in the heap. If you need to see which objects hold references to other objects, take a heap dump and analyze it with an appropriate tool.

A thread dump is also different from JFR: a thread dump is a point-in-time snapshot of stacks/states; JFR stores many events over time, making it useful for seeing what happened before, during, and after an incident.

## 3. When to create a JFR dump?

JFR is well suited for answering time-based questions:

- Which methods or threads consume the most CPU?
- When did garbage collection occur, and how long did pauses last?
- Which classes or call sites have increased allocation?
- Which threads are waiting long on monitors or synchronizers?
- Are there unusual numbers of exceptions, class loadings, or deoptimizations?
- Which file reads/writes or socket reads/writes have high latency?
- At what point did the application start slowing down?
- Which business steps took longer according to custom application events?

JFR is typically used in two scenarios:

1. **Time-fixed recording:** recording for a fixed duration to reproduce or measure a workload.
2. **Continuous recording:** maintaining a recording with size/time limits, then dumping the relevant portion of data when an incident occurs.

JFR has low overhead under an appropriate default configuration, but it is not zero. Configuring too many events, deep stack traces, or very low thresholds can increase CPU, memory, and file size.

## 4. Configuring default.jfc and profile.jfc

The JDK provides configuration templates in the `JAVA_HOME/lib/jfr` directory:

| Template | Characteristics | Usage |
|---|---|---|
| `default.jfc` | Collects a selected set of events with low overhead. | Long-running or continuous recordings. |
| `profile.jfc` | Collects more data, usually with additional profiling information. | Short recordings when deeper analysis is needed. |

When starting a recording with `jcmd`, you can choose:

~~~bash
jcmd <pid> JFR.start name=baseline settings=default
jcmd <pid> JFR.start name=profile-run settings=profile
~~~

The configuration name can be passed as a filename or a path to a `.jfc` file depending on the environment. Check `JAVA_HOME/lib/jfr` on the running JDK to see the available configurations.

Do not enable every event by default. Events with stack traces or very low thresholds can generate large amounts of data and increase overhead. Choose a configuration based on the question you need to investigate.

## 5. Lifecycle of a recording

A recording typically goes through these steps:

1. Find the PID of the JVM to monitor.
2. Start the recording with an appropriate event configuration.
3. Check whether the recording is running.
4. Dump a snapshot to a file when you need to save current data.
5. Continue the recording if you still need to collect more data.
6. Stop the recording to finish and save the final file.
7. Analyze the file using `jfr` or JMC.

JFR diagnostic commands are sent via `jcmd`. The `jcmd` tool must run on the same machine as the target JVM and usually requires the same effective user/group that started that JVM.

Find the JVM:

~~~bash
jcmd -l
~~~

Or:

~~~bash
jps -l
~~~

Once you have the PID, run the JFR commands against that process.

## 6. Starting a recording with jcmd JFR.start

Example of starting a recording named `incident`:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile
~~~

You can set disk size and age retention limits:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile disk=true maxage=30m maxsize=512M
~~~

Important options:

| Option | Meaning |
|---|---|
| `name` | Recording name used to reference it in subsequent commands. |
| `settings` | Event configuration file/profile, usually `default` or `profile`. |
| `disk` | Writes recording data to disk while collecting. |
| `duration` | Recording duration; `0s` means run until stopped. |
| `delay` | Wait period before starting the recording. |
| `filename` | Target file written when the recording ends. |
| `dumponexit` | Writes the recording to a file when the JVM shuts down. |
| `maxage` | Maximum age of data retained on disk. |
| `maxsize` | Maximum size of data retained on disk. |
| `path-to-gc-roots` | Collects paths to GC roots when the recording ends; may pause the application. |

Example of a recording that automatically stops after 5 minutes:

~~~bash
jcmd <pid> JFR.start name=short-profile settings=profile duration=5m filename=short-profile.jfr
~~~

Example of enabling dump on JVM shutdown:

~~~bash
jcmd <pid> JFR.start name=shutdown-capture settings=default dumponexit=true
~~~

To check specific options, run:

~~~bash
jcmd <pid> help JFR.start
~~~

## 7. Checking a recording with JFR.check

List running recordings:

~~~bash
jcmd <pid> JFR.check
~~~

Inspect a recording by name:

~~~bash
jcmd <pid> JFR.check name=incident
~~~

Show additional event settings:

~~~bash
jcmd <pid> JFR.check name=incident verbose=true
~~~

The output typically shows the recording ID, name, running/stopped state, max age, max size, and event configuration if verbose is enabled. Note the returned name or ID so you target the right recording when dumping or stopping.

If no recording matches the entered name, recheck the PID, name, and JVM state before running the next command.

## 8. Creating a snapshot with JFR.dump

`JFR.dump` writes the current data of a recording to a `.jfr` file:

~~~bash
jcmd <pid> JFR.dump name=incident filename=incident-snapshot.jfr
~~~

Important point: **JFR.dump does not stop the recording**. After the snapshot is written, the recording continues running and can be dumped again.

You can take multiple point-in-time snapshots:

~~~bash
jcmd <pid> JFR.dump name=incident filename=incident-01.jfr
jcmd <pid> JFR.dump name=incident filename=incident-02.jfr
~~~

Snapshots help compare data collected at different times. Include a timestamp or incident ID in the filename to avoid accidentally overwriting older files.

`JFR.dump` can select a time range or limit data using options such as `begin`, `end`, `maxage`, and `maxsize`. For example, to capture recent data:

~~~bash
jcmd <pid> JFR.dump name=incident maxage=15m filename=last-15-minutes.jfr
~~~

Time values can use seconds, minutes, or hours. Read `jcmd <pid> help JFR.dump` on your exact JDK to confirm supported options and timestamp formats.

## 9. Stopping a recording with JFR.stop

When enough data has been collected, stop the recording:

~~~bash
jcmd <pid> JFR.stop name=incident filename=incident-final.jfr
~~~

This command ends the recording and writes the remaining data to the target file. Afterward, the recording is no longer in the running state.

Verify:

~~~bash
jcmd <pid> JFR.check
~~~

Do not use `JFR.stop` just because you created a snapshot with `JFR.dump`; the two commands serve different purposes. Use dump to take a copy while continuing to record, and use stop when collection is complete.

## 10. Continuous recording and disk space management

Continuous recording is useful when incidents happen unpredictably. You can maintain a recording with the `default` configuration and size/age limits:

~~~bash
jcmd <pid> JFR.start name=continuous settings=default disk=true maxage=2h maxsize=1G
~~~

- `maxage` limits the age of retained data.
- `maxsize` limits the size of data on disk.
- When limits are reached, older data may be discarded to maintain a recent recording window.
- `disk=true` allows recording data to be written to disk during collection.

Without data limits, a long-running recording can consume significant disk space. Set limits based on event rate, available storage, and how much history you need to retain.

Do not set `maxsize` too small compared to the maximum chunk size configured in JFR. Run `jcmd <pid> JFR.configure` to check `maxchunksize`, repository path, and related parameters.

## 11. JFR repository and recording storage locations

During a recording, JFR may write chunks to a temporary disk repository. The repository is not the final dump file that analysts typically share or open in JMC.

Some JFR configuration parameters:

- `repositorypath`: location for temporary chunks.
- `dumppath`: location where recordings are written if the JVM encounters a fatal error.
- `preserve-repository`: determines whether to keep the repository after the JVM exits.
- `memorysize`: total JFR buffer memory.
- `maxchunksize`: maximum size of a single chunk.
- `stackdepth`: stack trace depth recorded.

View configuration:

~~~bash
jcmd <pid> JFR.configure
~~~

Set the repository path:

~~~bash
jcmd <pid> JFR.configure repositorypath=/var/tmp/jfr-repository
~~~

Parameters such as memory size, max chunk size, and stack depth have restrictions on changing after JFR has been initialized. Do not arbitrarily change buffers or thread buffers in production, as this can affect performance.

If the JVM crashes and only repository chunks remain, the `jfr assemble` tool can combine the remaining chunks into a recording when the repository is intact and the data is still valid.

## 12. Getting a file overview with jfr summary

Once you have a file, verify its validity and overview contents:

~~~bash
jfr summary incident-final.jfr
~~~

The command displays:

- Recording format version.
- Number of chunks.
- Start time and duration.
- List of event types.
- Event count per type.
- Data size of each event type.

For example, if the file has many `jdk.GarbageCollection`, `jdk.ObjectAllocationSample`, or `jdk.JavaMonitorEnter` events, you can filter those events to investigate GC, allocation, or lock contention.

`jfr summary` is a quick check before deep analysis. If the file is empty, corrupted, or missing expected events, check the recording settings and start/end times.

## 13. Printing events with jfr print

Use `jfr print` to read events in text form:

~~~bash
jfr print incident-final.jfr
~~~

It is best to filter by event to reduce output:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause incident-final.jfr
~~~

Filter by category:

~~~bash
jfr print --categories "GC,JVM,Java*" incident-final.jfr
~~~

Limit stack trace depth:

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 32 incident-final.jfr
~~~

Export as JSON:

~~~bash
jfr print --json --events jdk.GarbageCollection incident-final.jfr
~~~

Export as XML:

~~~bash
jfr print --xml --events jdk.GarbageCollection incident-final.jfr
~~~

JSON/XML is useful for further processing with scripts. Display format depends on the JDK version and event metadata; avoid assuming all JFR files have the exact same fields.

## 14. Summarizing with jfr view

`jfr view` displays event data as summary tables. Some commonly used views:

| View | Purpose |
|---|---|
| `hot-methods` | Shows methods appearing most frequently in samples. |
| `gc-pauses` | Analyzes GC-related pauses. |
| `allocation-by-class` | Shows allocations by class. |
| `allocation-by-site` | Shows allocations by code site. |
| `contention-by-class` | Summarizes contention by class. |
| `thread-cpu-load` | Observes CPU load per thread. |
| `file-reads-by-path` | Summarizes file reads by path. |
| `socket-reads-by-host` | Summarizes socket reads by host. |

Examples:

~~~bash
jfr view hot-methods incident-final.jfr
jfr view gc-pauses incident-final.jfr
jfr view allocation-by-class incident-final.jfr
~~~

Available view names depend on the JDK. Use `jfr help view` or `jfr view all-views <file>` to see the list for your version.

## 15. Inspecting metadata and customizing JFR events

Metadata describes event types and fields:

~~~bash
jfr metadata incident-final.jfr
~~~

Filter metadata by event:

~~~bash
jfr metadata --events jdk.GarbageCollection incident-final.jfr
~~~

JFR uses `.jfc` configuration files to specify which events are enabled, thresholds, stack traces, and related options.

Create a custom configuration from the profile template:

~~~bash
jfr configure --input profile.jfc --output custom.jfc
~~~

You can adjust event settings, for example:

~~~bash
jfr configure --input profile.jfc --output custom.jfc jdk.JavaMonitorEnter#threshold=10ms
~~~

Then start a recording with the configuration file:

~~~bash
jcmd <pid> JFR.start name=custom-profile settings=custom.jfc
~~~

Event configuration should align with the question under investigation. Enabling too many events or setting thresholds too low can increase file size and overhead.

## 16. Filtering data before sharing with jfr scrub

A JFR file may contain internal information such as environment variables, system properties, file paths, thread names, hostnames, command lines, or stack traces. Before sending a file outside your team, inspect its contents and remove unnecessary events.

`jfr scrub` creates a new recording after filtering events, categories, or threads:

~~~bash
jfr scrub --exclude-events jdk.InitialEnvironmentVariable,jdk.InitialSystemProperty incident-final.jfr incident-scrubbed.jfr
~~~

Keep only a specific set of events:

~~~bash
jfr scrub --include-events jdk.GarbageCollection,jdk.ExecutionSample incident-final.jfr focused.jfr
~~~

Exclude a category:

~~~bash
jfr scrub --exclude-categories OS incident-final.jfr no-os-events.jfr
~~~

Filter by thread:

~~~bash
jfr scrub --include-threads main incident-final.jfr main-thread-only.jfr
~~~

Scrubbing produces a filtered output file; keep the original in controlled storage if full analysis is still needed. Scrubbing does not replace manually reviewing for any remaining sensitive data.

## 17. Assembling and splitting recordings

A recording can consist of multiple chunks. Advanced commands:

~~~bash
jfr assemble <repository> assembled.jfr
~~~

Use `assemble` to combine remaining chunks in a disk repository into a recording file.

Split a large recording into smaller files:

~~~bash
jfr disassemble --output chunks incident-final.jfr
~~~

You can adjust the number of chunks or maximum size per file:

~~~bash
jfr disassemble --max-chunks 2 --output chunks incident-final.jfr
~~~

`disassemble` is only useful when the recording has enough chunks to split. A small file with only one chunk may not need or be able to split under default limits. Run `jfr help assemble` and `jfr help disassemble` to see the exact syntax for your JDK.

## 18. Analyzing with Java Mission Control

Java Mission Control (JMC) is a graphical interface for analyzing JFR recordings. Open a `.jfr` file in JMC to view summary pages and drill down into events.

A typical workflow:

1. Open the recording in JMC.
2. Check the overview to observe CPU, heap, GC, and threads.
3. Open Java Application to inspect hot methods, allocations, and lock contention.
4. Open Garbage Collections to inspect pauses, collector behavior, and heap usage.
5. Open Threads to investigate thread samples, parks, and monitor waits.
6. Open I/O to inspect file/socket events.
7. Select an event or time range to view stack traces and detailed fields.

JMC is well suited for interacting with large datasets and correlating multiple events. The `jfr` CLI is ideal for quick checks, filtering events, and automating processing steps.

## 19. Creating a JFR dump with the Java Flight Recorder API

Applications can create recordings directly using the API in the `jdk.jfr` module. This is useful when you want to control start/stop timing, add custom events, or integrate recording into a test workflow.

The example below creates a `demo.Work` event and records 10 batch processing iterations to a file.

File `src/com/acme/WorkEvent.java`:

~~~java
package com.acme;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("demo.Work")
@Label("Demo Work")
@Category({"Demo", "JFR"})
class WorkEvent extends Event {
    @Label("Operation")
    String operation;

    @Label("Item Count")
    int itemCount;
}
~~~

File `src/com/acme/JfrDumpDemo.java`:

~~~java
package com.acme;

import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public class JfrDumpDemo {
    public static void main(String[] args) throws Exception {
        Path output = Path.of(args[0]);

        try (Recording recording =
                new Recording(Configuration.getConfiguration("profile"))) {
            recording.setName("jfr-dump-demo");
            recording.setToDisk(true);
            recording.enable(WorkEvent.class)
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();

            recording.start();

            for (int i = 1; i <= 10; i++) {
                WorkEvent event = new WorkEvent();
                event.operation = "process-batch";
                event.itemCount = i * 10;

                event.begin();
                Thread.sleep(25);
                event.end();
                event.commit();
            }

            recording.stop();
            recording.dump(output);
            System.out.println("JFR_DUMP_CREATED=" + output.getFileName());
        }
    }
}
~~~

The event class is named `WorkEvent`, while the metadata registers the event under the name `demo.Work`. Both `operation` and `itemCount` fields are saved along with timestamp, duration, thread, and stack trace if the event settings enable stack traces.

## 20. Compiling and running the Java 17+ example

From the project root directory:

~~~bash
javac --release 17 -d out \
  src/com/acme/WorkEvent.java \
  src/com/acme/JfrDumpDemo.java
~~~

Run the program and specify the target file:

~~~bash
java -cp out com.acme.JfrDumpDemo demo-recording.jfr
~~~

Exact stdout:

~~~text
JFR_DUMP_CREATED=demo-recording.jfr
~~~

Inspect the file:

~~~bash
jfr summary demo-recording.jfr
~~~

Print custom events:

~~~bash
jfr print --events demo.Work demo-recording.jfr
~~~

View the event table:

~~~bash
jfr view demo.Work demo-recording.jfr
~~~

View metadata:

~~~bash
jfr metadata --events demo.Work demo-recording.jfr
~~~

In a test run on Azul OpenJDK 24.0.2, the program compiled with `javac --release 17`, created `demo-recording.jfr`, and recorded exactly 10 `demo.Work` events. The `jfr print` command displayed the `process-batch` operation, `itemCount` values from 10 to 100, and the stack trace at `JfrDumpDemo.main`.

## 21. Complete workflow example for a running JVM

Suppose a Java application is already running and you want to record data while reproducing an issue.

Find the PID:

~~~bash
jcmd -l
~~~

Start the recording:

~~~bash
jcmd 12345 JFR.start name=incident settings=profile disk=true maxage=30m maxsize=512M
~~~

Check status:

~~~bash
jcmd 12345 JFR.check name=incident
~~~

While the issue is occurring, take a snapshot:

~~~bash
jcmd 12345 JFR.dump name=incident filename=incident-snapshot.jfr
~~~

The recording continues running. If further observation is needed, wait a bit longer and dump a second snapshot. Once enough data is collected:

~~~bash
jcmd 12345 JFR.stop name=incident filename=incident-final.jfr
~~~

Analyze:

~~~bash
jfr summary incident-snapshot.jfr
jfr view hot-methods incident-snapshot.jfr
jfr view gc-pauses incident-snapshot.jfr
jfr print --events jdk.GarbageCollection incident-final.jfr
~~~

PID `12345` is just an example; replace it with the actual PID. If the recording has already stopped automatically due to duration or JVM shutdown, check the target file and status before calling stop again.

## 22. Security and protecting JFR dump files

JFR files may contain sensitive data from the environment and application. Before sharing:

- Check `jdk.InitialEnvironmentVariable` and `jdk.InitialSystemProperty` events.
- Review file paths, hostnames, command lines, and thread names.
- Verify that custom events do not accidentally record tokens, user data, or business payloads.
- Restrict read permissions on the file and storage directory.
- Encrypt the file when storing or transferring over supported systems.
- Use `jfr scrub` to remove unnecessary events before sending.
- Keep the original in internal storage if further investigation is needed.

Do not record passwords, access tokens, session IDs, or personal data in custom events. Stack traces and system properties can also reveal package names, deployment directories, or internal configuration.

## 23. Overhead, limitations, and compatibility

JFR is designed for profiling and troubleshooting with low overhead under appropriate settings, though the impact depends on event settings and workload.

Key considerations:

- `default.jfc` is generally suitable for long recordings; `profile.jfc` collects more information and is usually intended for shorter durations.
- Enabling stack traces for many events can increase file size and CPU usage.
- Disk recordings require sufficient temporary space and target file space.
- `path-to-gc-roots` can pause the application; enable it only when suspecting a memory leak.
- JFR files use a binary format; use a compatible JDK/JMC to analyze them.
- Event types and fields may vary by JDK, vendor, collector, and configuration.
- A recording alone does not prove root cause; correlate it with logs, metrics, request traces, and workload context.
- `jcmd` must run on the same machine with an account permitted to attach to the target JVM.
- In containers, identify the PID in the proper namespace and run tools from an environment that can see the process.

A JFR dump typically shows what happened inside the JVM, but it does not replace heap object graph analysis, network traces, or distributed tracing when the issue lies outside the collected events.

## 24. Troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| `jcmd` cannot find the JVM | Wrong PID, different user, JVM in another container namespace, or attach disabled. | Use `jcmd -l`, verify user/PID, and check container environment. |
| `JFR.start` reports recording already exists | A recording with the same name already exists or is running. | Use `JFR.check`, choose another name, or stop the old recording if confirmed unnecessary. |
| Cannot create dump file | Invalid path, missing write permissions, or disk full. | Choose a writable directory, check disk space, and verify the path. |
| `.jfr` file is very small | Recording too short, event settings did not enable needed events, or workload did not trigger events. | Check `JFR.check verbose=true`, settings, and collection duration. |
| `jfr summary` cannot read file | File truncated, write incomplete, or not a valid JFR recording. | Check dump/stop command, file size, and retry with a fully written file. |
| Expected events are missing | Event disabled, threshold too high, or did not occur during recording. | Check `.jfc`, metadata, and event settings; extend recording if appropriate. |
| Recording consumes too much space | Profile too detailed, high event rate, or no limits set. | Use default settings, set maxage/maxsize, and filter needed events. |
| JMC cannot open the file | Incomplete file or JMC version does not support the recording format. | Verify with `jfr summary`, use a matching JMC/JDK, and regenerate the dump if needed. |
| File contains sensitive data | Events recorded environment, system properties, or application data. | Do not share the original; scrub and review the output file. |

## 25. Recommended workflow

When facing a Java performance incident:

1. Identify the JVM, PID, and process-owning user.
2. Choose `default` for long observation or `profile` for short profiling.
3. Start a recording with a clear name and maxage/maxsize limits.
4. Use `JFR.check` to confirm the recording is running.
5. Reproduce the workload or wait for the issue to occur.
6. Use `JFR.dump` to capture a snapshot without stopping the recording.
7. When enough data is collected, use `JFR.stop` to finish and save the final file.
8. Verify the file with `jfr summary`.
9. Use `jfr view`, `jfr print`, or JMC to analyze relevant events.
10. Scrub sensitive data before sharing.
11. Save the recording, event configuration, and collection timestamps so the analysis can be reproduced.

A JFR dump file provides structured evidence of JVM behavior over time. By understanding the recording lifecycle, distinguishing dump from stop, knowing how to read files, and protecting sensitive data, you can use JFR to investigate performance systematically.

## References

- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html).
- Oracle JDK 24 — [The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html).
- Oracle JDK 24 — [Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html).
- Oracle JDK 24 — [Flight Recorder API Programmer's Guide](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/package-summary.html).

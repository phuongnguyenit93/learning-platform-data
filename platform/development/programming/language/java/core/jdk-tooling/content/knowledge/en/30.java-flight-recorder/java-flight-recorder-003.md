# Stopping a Java Flight Recorder Recording

## 1. What does stopping a recording mean?

**Java Flight Recorder (JFR)** collects JVM runtime events into a recording. Depending on the configuration, the data can include CPU, threads, allocations, garbage collection (GC), class loading, I/O, and other activity.

Stopping a recording ends data collection for a specific recording. The JVM and Java application continue running normally.

When stopping, you need to decide whether the data will be saved to a `.jfr` file or discarded. A stop command can complete a recording successfully without creating a file if no destination is specified.

For a running JVM, the common approach is to use the `jcmd` diagnostic command:

~~~bash
jcmd <pid> JFR.stop name=<recording-name> filename=<path-to-file>
~~~

The recording name and PID must belong to the exact JVM you intend to operate on. Check the status before stopping to avoid terminating the wrong recording.

## 2. Distinguishing JFR.stop, JFR.dump, and the jfr command

These three operations serve different purposes:

| Tool/Command | Purpose |
|---|---|
| jcmd PID JFR.check | View running recordings and their names. |
| jcmd PID JFR.dump | Write a copy of the current data to a file; the recording continues running. |
| jcmd PID JFR.stop | Stop the selected recording and finalize saving data if a destination is set. |
| jfr summary file.jfr | Read summary information of a created recording file. |
| jfr print file.jfr | Print events in the file according to the selected filter. |

**JFR.dump does not stop the recording.** It creates a snapshot at the time of the dump so you can inspect data while collection continues. Use `JFR.stop` when you want to end the recording and finalize the data.

The `jfr` command-line tool processes recording files. On JDK 24.0.2, `jfr help` does not include a `jfr stop` command. Controlling a running recording is done with `jcmd` or the Java Flight Recorder API.

## 3. Finding the PID and identifying running recordings

First, find the target JVM:

~~~bash
jcmd -l
~~~

Example:

~~~text
12345 com.example.orders.OrderApplication
~~~

Check the active recordings:

~~~bash
jcmd 12345 JFR.check
~~~

Example output:

~~~text
12345:
Recording 1: name=OrdersProfile maxsize=250.0MB (running)
Recording 2: name=ContinuousMonitoring maxage=1h maxsize=512.0MB (running)
~~~

The names and IDs in the example are for illustration only. A JVM can run multiple recordings concurrently, each with its own name and configuration.

You can filter by name:

~~~bash
jcmd 12345 JFR.check name=OrdersProfile
~~~

To also print event settings:

~~~bash
jcmd 12345 JFR.check name=OrdersProfile verbose=true
~~~

Get the exact name from the output of `JFR.start` or `JFR.check`. Do not guess the recording name and do not reuse an old PID after a process has restarted.

## 4. Checking the JFR.stop syntax of the target JVM

Before running it, check the command help:

~~~bash
jcmd 12345 help JFR.stop
~~~

On JDK 24.0.2, the syntax is:

~~~text
JFR.stop [options]

filename  (Optional) Name of the file to which the recording is written
          when the recording is stopped.
name      Name of the recording.
~~~

The two options:

- **name:** name of the recording to stop. This option is required to select the recording.
- **filename:** path to the `.jfr` file that receives the data on stop; it can be passed at `JFR.stop` or configured at `JFR.start`.

`JFR.stop` has Impact: Low on JDK 24.0.2. Even so, verify the PID, recording name, and output destination before running it in production.

If you call `JFR.stop` without `name`, no recording is selected to stop. The command does not mean stopping all recordings.

## 5. Stopping a recording and saving the file immediately

The clearest approach is to pass both the name and the file path:

~~~bash
jcmd 12345 JFR.stop name=OrdersProfile filename=C:\recordings\orders-profile.jfr
~~~

Example response:

~~~text
12345:
Stopped recording "OrdersProfile", 12.4 MB written to:

C:\recordings\orders-profile.jfr
~~~

Actual file names, sizes, and PIDs will vary.

When the command returns successfully, the JVM has stopped the selected recording and written the final data to the file. Verify that the file exists, has a size greater than 0, and is readable before moving on to analysis.

The destination path must exist or be creatable according to the environment's rules, the account running the JVM must have write permission, and the disk must have enough free space. Use an absolute path to avoid ambiguity with the process working directory.

## 6. Configuring filename when starting a recording

You can set the destination file at start time:

~~~bash
jcmd 12345 JFR.start name=OrdersProfile settings=default disk=true filename=C:\recordings\orders-profile.jfr
~~~

Then check:

~~~bash
jcmd 12345 JFR.check name=OrdersProfile
~~~

When you want to finish early:

~~~bash
jcmd 12345 JFR.stop name=OrdersProfile
~~~

If `filename` was configured at `JFR.start`, `JFR.stop` can use that destination even without passing `filename` again. This behavior has been verified on JDK 24.0.2.

This is convenient when the output location is known in advance. If `filename` was not set at start time, pass `filename` in the stop command to ensure the data is saved.

## 7. What happens if filename is omitted?

`JFR.stop` can stop a recording without saving the data to a file.

Practical rules:

- If `filename` was configured at `JFR.start`, the stop command finalizes into that file.
- If `filename` was not configured at `JFR.start`, you can pass `filename` to `JFR.stop`.
- If no destination is provided at either time, the recording data is discarded when stopped.

Example of stopping and discarding data:

~~~bash
jcmd 12345 JFR.stop name=TemporaryCheck
~~~

Use this only when you intentionally do not need to keep the recording. If you need to investigate an issue or hand the data off to someone else, save the file before stopping.

On JDK 24.0.2, testing a recording with no `filename` at start and no `filename` at stop confirmed that `JFR.stop` returns success without creating a `.jfr` file in the test directory.

## 8. Using JFR.dump to save a snapshot while continuing to record

Sometimes you need to inspect current data immediately while keeping the recording collecting. In that case, use `JFR.dump`:

~~~bash
jcmd 12345 JFR.dump name=OrdersProfile filename=C:\recordings\orders-snapshot.jfr
~~~

Check the status again:

~~~bash
jcmd 12345 JFR.check name=OrdersProfile
~~~

The recording remains in the `running` state after `JFR.dump`. The snapshot file contains data recorded up to the time of the dump; new events continue to be collected into the running recording.

After taking a snapshot, you can continue observing and stop the recording later:

~~~bash
jcmd 12345 JFR.stop name=OrdersProfile filename=C:\recordings\orders-final.jfr
~~~

Use different file names for the snapshot and the final file to avoid overwriting data. If you do not specify `name` for `JFR.dump`, the command may dump data from all recordings; explicitly specify the recording name when the JVM runs multiple recordings.

## 9. Choosing when to stop a recording

Stopping too early can leave the file without enough data to reproduce the issue. Stopping too late can make the file larger and increase storage costs.

A reasonable workflow:

1. Identify the event or time window to observe.
2. Check the recording name and settings.
3. Wait until the symptom under investigation has occurred.
4. Note the timestamp and workload context.
5. Stop the recording and save the file.
6. Verify that the file is complete before analyzing it.

If you know the collection duration in advance, you can configure `duration` at start time:

~~~bash
jcmd 12345 JFR.start name=ShortProfile settings=profile duration=5m filename=C:\recordings\short-profile.jfr
~~~

The JVM will automatically end the recording after the configured duration. If you need to end it sooner, use `JFR.stop` with the exact recording name.

## 10. Choosing settings and size limits before starting

Stopping a recording is only part of lifecycle management. Configuration at start time affects file size, event types, and overhead.

Two commonly used built-in configurations:

- **default:** collects a baseline set of events with low overhead, suitable for continuous recordings.
- **profile:** collects more data with higher overhead; suitable for short investigation windows when more detail is needed.

Examples:

~~~bash
jcmd 12345 JFR.start name=Continuous settings=default maxage=1h maxsize=512M filename=C:\recordings\continuous.jfr
~~~

~~~bash
jcmd 12345 JFR.start name=ShortProfile settings=profile maxsize=256M filename=C:\recordings\short-profile.jfr
~~~

Related options:

| Option | Meaning |
|---|---|
| name | Name the recording for checking, dumping, and stopping. |
| settings | Select the event configuration, such as default or profile. |
| filename | File path used when the recording stops. |
| duration | Recording duration before stopping automatically. |
| delay | Wait for a period of time before starting. |
| maxage | Maximum age of data kept on disk when disk recording is enabled. |
| maxsize | Maximum size of data kept on disk. |
| dumponexit | Write the recording to a file when the JVM shuts down. |
| disk | Enable writing data to disk while the recording runs. |

`JFR.start` has Impact: Medium on JDK 24.0.2, and actual impact depends on settings. Do not default to `profile` for long-running recordings without evaluating the overhead.

## 11. Inspecting the file after stopping

After `JFR.stop` completes, inspect the file with `jfr`:

~~~bash
jfr summary C:\recordings\orders-profile.jfr
~~~

`summary` displays:

- Recording format version.
- Number of chunks.
- Start time and duration.
- Event count per type.
- Event size.

If you need to inspect specific events:

~~~bash
jfr print --events jdk.ExecutionSample C:\recordings\orders-profile.jfr
~~~

You can inspect other events such as GC, thread, allocation, or class loading by changing the event filter. Not every event will have data; results depend on the settings and actual activity during the recording.

If the file cannot be read, check the path, size, and the output message from `JFR.stop`. Make sure the recording has stopped and the file has finished writing before analyzing it.

## 12. Complete example with jcmd

Create **JfrStopProbe.java**:

~~~java
public class JfrStopProbe {
    public static void main(String[] args) throws Exception {
        System.out.println(
                "JfrStopProbe ready; pid=" + ProcessHandle.current().pid());

        long end = System.nanoTime() + 120_000_000_000L;
        long count = 0;

        while (System.nanoTime() < end) {
            byte[] payload = new byte[128 * 1024];
            payload[0] = (byte) count++;
            Thread.sleep(20);
        }
    }
}
~~~

Compile:

~~~bash
javac --release 17 -encoding UTF-8 JfrStopProbe.java
~~~

Run:

~~~bash
java JfrStopProbe
~~~

Example stdout:

~~~text
JfrStopProbe ready; pid=12345
~~~

Open a second terminal. Replace the PID with the actual value and start the recording:

~~~bash
jcmd 12345 JFR.start name=StopPractice settings=default disk=true
~~~

Check the status:

~~~bash
jcmd 12345 JFR.check name=StopPractice
~~~

Stop and save:

~~~bash
jcmd 12345 JFR.stop name=StopPractice filename=C:\recordings\stop-practice.jfr
~~~

Verify the file:

~~~bash
jfr summary C:\recordings\stop-practice.jfr
~~~

On JDK 24.0.2, `JfrStopProbe` was compiled with `javac --release 17`. `JFR.start`, `JFR.check`, `JFR.dump`, and `JFR.stop` all ran successfully; both the snapshot file and the final file were read successfully by `jfr summary`.

After practicing, stop the sample program with `Ctrl+C`.

## 13. Stopping a recording with the Java Flight Recorder API

An application can also manage recordings programmatically using the API in the `jdk.jfr` module.

Main steps:

- Create a `Recording` with an event configuration.
- Call `start()` to begin collection.
- Call `stop()` to end collection.
- Call `dump(Path)` to save the collected data.
- Close the `Recording` to release resources.

Java 17+ example:

~~~java
import java.nio.file.Path;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public class ProgrammaticJfrStop {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("programmatic-stop.jfr");

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("default"))) {
            recording.setName("ProgrammaticStop");
            recording.start();

            Thread.sleep(1500);

            recording.stop();
            recording.dump(output);

            System.out.println(
                    "Recording stopped and saved: " +
                    output.toAbsolutePath());
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 ProgrammaticJfrStop.java
java ProgrammaticJfrStop
~~~

Output looks like:

~~~text
Recording stopped and saved: <absolute-path>\programmatic-stop.jfr
~~~

The absolute path depends on the directory from which the program is run.

`stop()` ends collection, while the recording object still retains its data for dumping. `dump(Path)` writes that data to a file. The `try-with-resources` block calls `close()` on exit to release resources. If you need to keep the data, dump it before closing the recording.

This example was compiled and run on JDK 24.0.2 using Java 17-compatible source code; the generated file was verified with `jfr summary`.

## 14. Distinguishing stopping a recording from JVM shutdown

`JFR.stop` stops only the selected recording. `JFR.stop` does not stop the JVM, restart the JVM, or shut down the application.

It also does not stop other running recordings. If the JVM has multiple recordings, each recording must be selected by name.

If the JVM shuts down, recordings with `dumponexit=true` can be written to a file according to their configuration. This is a mechanism for saving on process exit, distinct from stopping a recording while the JVM keeps running.

Example of configuring dump on JVM shutdown:

~~~bash
jcmd 12345 JFR.start name=ShutdownCapture settings=default dumponexit=true
~~~

If you want to finalize data immediately while the application keeps running, use `JFR.stop`. If you want to retain the recording until JVM shutdown, configure `dumponexit` appropriately and ensure the output path is writable.

## 15. Permissions, paths, and file security

`jcmd` must attach to the target JVM. Common requirements:

- Run `jcmd` on the same machine as the JVM.
- Use an account with permission to attach to the target process.
- On Unix, the user and effective group must match the process owning the JVM.
- The attach mechanism must not be disabled.
- In containers, run from the appropriate PID namespace and an environment that can see the JVM.

The file path must be writable by the JVM process. Having write permission in a terminal does not guarantee that a JVM running under a different account has the same permission.

Apply the principle of least privilege: grant attach permission and recording read access only to people who actually need to diagnose that process.

JFR files can contain thread names, class names, stack traces, file paths, I/O details, and other operational data depending on event settings. Treat recording files as sensitive diagnostic data:

- Store them in a directory with restricted access.
- Do not attach raw files to tickets or public places without authorization.
- Delete or archive them according to your retention policy.
- Do not overwrite important files with another recording.
- Check available disk space before dumping a large recording.

## 16. Common errors when stopping a recording

| Symptom | Possible Cause | Resolution |
|---|---|---|
| jcmd cannot find the PID | Wrong PID or the JVM has exited. | Run `jcmd -l` and re-verify the process. |
| Recording not found | Wrong name, recording already stopped, or auto-generated name. | Run `JFR.check` and use the exact `name`. |
| JFR.stop did not stop the expected recording | Wrong recording selected or `name` option omitted. | Check the list and specify `name` explicitly. |
| JFR.stop succeeded but no file was created | `filename` was not configured at start or stop. | Pass `filename` to `JFR.stop` or set `filename` at `JFR.start`. |
| Permission denied when saving | The JVM user lacks write permission to the target directory. | Choose a directory the JVM account is allowed to write to. |
| .jfr file is empty or unreadable | Dump did not complete, file was interrupted, or wrong path. | Check the stop message, verify file size, and run `jfr summary`. |
| Recording is still running after JFR.dump | Expected behavior: dump only creates a snapshot. | Use `JFR.stop` when you need to end the recording. |
| File is too large | Long recording, `profile` settings, or unsuitable size limits. | Set `duration`, `maxage`, `maxsize`, and choose appropriate settings. |
| Attach failure | Different user, namespace, or attach mechanism disabled. | Check process owner, container setup, and JVM configuration. |
| jfr reports unknown command stop | Using the `jfr` CLI to control a live recording. | Use `jcmd PID JFR.stop`; `jfr` is for reading and processing files. |
| Recording stopped but data is insufficient | Stopped before the symptom under investigation occurred. | Check duration, event settings, and workload context. |

## 17. Safe operating procedure

Before stopping a recording in a live environment:

1. Identify the JVM and the latest PID.
2. Run `JFR.check` to see recording names and statuses.
3. Select the right recording for your investigation goal.
4. Check whether `filename` was already set at start time.
5. Verify write permissions and available disk space.
6. If you need a snapshot while continuing collection, use `JFR.dump`.
7. If you need to finish, use `JFR.stop` with the exact `name` and `filename`.
8. Read the `jcmd` response to confirm the recording stopped and data was written.
9. Run `jfr summary` to verify the file.
10. Store the file according to access and retention policies.
11. End the investigation session only after confirming the data is preserved.

If the JVM is running multiple recordings, stop each one individually by its verified name. Never assume a single `JFR.stop` command will stop them all.

## 18. Checklist before ending a recording

- [ ] Verified the exact PID of the JVM.
- [ ] Ran `JFR.check` and confirmed the recording name.
- [ ] Selected the right recording to stop.
- [ ] Checked whether `filename` was configured at start or will be passed at stop.
- [ ] Confirmed the target directory is writable and has enough space.
- [ ] Distinguished `JFR.dump` from `JFR.stop`.
- [ ] Understood that stop does not stop the JVM or other recordings.
- [ ] Reviewed the success response from `jcmd`.
- [ ] Confirmed the `.jfr` file exists and has a reasonable size.
- [ ] Ran `jfr summary` to confirm the file is readable.
- [ ] Protected the recording file as sensitive diagnostic data.
- [ ] Checked that no unintended recordings remain running.

## 19. References

- Oracle JDK 24 — The jcmd Command, `JFR.start`, `JFR.check`, `JFR.dump`, and `JFR.stop`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Oracle JDK 24 — Diagnostic Tools, Java Flight Recorder section: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Java SE 24 API — `jdk.jfr.Recording`: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Recording.html

Stopping a recording properly comes down to three things: confirming the right recording, choosing the output location explicitly, and verifying the file afterward. Use `JFR.check` to identify it, `JFR.stop` to finish it, `JFR.dump` to take a snapshot while continuing to record, and `jfr summary` to confirm the file is ready for analysis.
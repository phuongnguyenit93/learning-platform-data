# 14.7 Managing `duration`, `maxage`, `maxsize`, `repository`, and Dump on Exit

## 1. The Big Picture: Lifecycle of a JFR Recording

**Java Flight Recorder (JFR)** collects events about JVM and application activity using the chosen configuration. In HotSpot JDK 17+, you can start a recording at JVM launch or control a running JVM with `jcmd`. To gather useful data without letting disk usage grow unbounded, you must understand five distinct concepts:

1. **`duration`:** how long a recording runs before stopping automatically.
2. **`maxage`:** how far back in time on disk history is retained.
3. **`maxsize`:** cap on the amount of a recording's data retained in the disk repository.
4. **`repository`:** temporary directory storing *chunks* during collection; distinct from the exported `.jfr` file for analysis.
5. **`dumponexit`:** attempts to export data from a **still-running** recording when the JVM shuts down cleanly.

These mechanisms belong to **different management layers**, not five names for the same limit. A long-running recording can run indefinitely while retaining only the last 30 minutes; a 2-minute investigative recording can auto-stop and write a file; a recording with dump-on-exit enabled can export when the app exits even before its scheduled stop.

### Two Storage Layers to Distinguish

```text
Events emitted inside the JVM
         |
         v
In-memory JFR buffers
         |
         | disk=true: incrementally writes chunks
         v
JVM temporary repository  <--- maxage / maxsize bound retained history
         |
         | JFR.dump / JFR.stop filename=...
         | or auto-stop / dumponexit + filename=...
         v
Exported .jfr file        <--- must be verified, backed up, and managed separately
         |
         v
jfr summary / JDK Mission Control / analysis tools
```

**Crucial point:** a recording's `maxage` and `maxsize` act on **data retained in the repository**; they do not automatically set a lifetime or max size across all previously exported `.jfr` files. Once an old chunk has been evicted, a later `JFR.dump` cannot recover it.

## 2. Quick Reference: Which Parameter Controls What?

| Option | Scope | Example Value | Meaning When Used |
| --- | --- | --- | --- |
| `duration` | One recording, at `JFR.start` or `-XX:StartFlightRecording` | `2m` | Auto-stops after two minutes of collection. `0s`: runs with no time limit. |
| `maxage` | History **in the repository** for one recording when `disk=true` | `30m` | Keeps roughly up to the last 30 minutes of data, managed by chunks; `0s`: no age limit. |
| `maxsize` | History **in the repository** for one recording when `disk=true` | `256m` | Keeps roughly the configured byte limit of data; `0`: no size limit. |
| `disk` | One recording | `true` | Allows continuous persistence to the repository; `JFR.start` defaults to `true`. |
| `repositorypath` | JVM-wide JFR setting via `JFR.configure` | `/tmp/jfr-repo` | Temporary directory holding chunks. |
| `repository` | JVM startup setting via `-XX:FlightRecorderOptions` | `/tmp/jfr-repo` | Same temporary directory role, different flag syntax. |
| `filename` | Output target on recording stop / dump-on-exit or `JFR.dump` | `/tmp/jfr-out/incident.jfr` | Output file, requires write permission; path is resolved by the **target JVM**. |
| `dumponexit` | One recording | `true` | Exports when the JVM shuts down cleanly, **if the recording is still running**; defaults to `false`. |
| `JFR.dump maxage/maxsize` | Single **export** call | `maxage=10m` | Selects a subset of still-available data to export; **does not alter the retention policy** of the running recording. |
| `preserve-repository` | JVM-wide JFR setting | `true`/`false` | Controls whether temporary chunks remain after JVM exit; defaults to `false`. **Does not replace a verified exported file.** |

Per JDK 21 `jcmd` documentation, `JFR.start` defaults to `duration=0s`, `maxage=0s`, and `maxsize=0`—meaning **all three are unbounded** unless you specify them explicitly. When keeping long-running recordings, proactively configure storage limits.

**Valid units in the examples:**

- Durations typically use suffixes `s` (seconds), `m` (minutes), `h` (hours); choose formats supported by your exact command version. E.g., `duration=90s`, `maxage=1h`.
- `maxsize=256m` uses size suffixes `m/M`; `g/G` for larger sizes. Do not mistakenly pass `256ms` (milliseconds) as a size.
- `maxsize` must be **no smaller than `maxchunksize`** configured in JFR; JDK 21's default `maxchunksize` is around `12M` and can be customized. Do not configure a ring with `maxsize=1m` and expect it to work.

## 3. Choosing Among Three Recording Patterns for Practical Needs

### 3.1. Bounded Recording to Investigate a Phenomenon

To measure for two minutes and auto-export as `.jfr`:

```bash
jcmd 12345 JFR.start name=incident settings=profile duration=2m disk=true filename=/tmp/jfr-out/incident-%p-%t.jfr
```

- `duration=2m`: two minutes after the recording actually starts, it stops automatically. No need to wait for the application to exit.
- `settings=profile`: captures more events than `default`, suited for targeted investigation but may incur higher overhead.
- `filename`: where to write the file when the recording stops. Tokens `%p` and `%t` are substituted by HotSpot with PID and timestamp per docs; use distinct names to avoid overwriting.
- `disk=true`: allows storing chunks on disk. **Whether the file can be written still depends on the target JVM's directory, permissions, and free space.**

If the process exits **before the 2 minutes finish**, the command above has not enabled `dumponexit`. To capture data if the process shuts down cleanly early, add `dumponexit=true`:

```bash
jcmd 12345 JFR.start name=incident_early_exit settings=profile duration=2m disk=true dumponexit=true filename=/tmp/jfr-out/incident-exit-%p-%t.jfr
```

Do not launch both examples concurrently for the same purpose in a real application; these are two **alternative configurations**. Once a recording's `duration` has expired, it is **no longer running** to trigger dump-on-exit at a later time.

### 3.2. Continuous Rolling-History Recording

To keep a process running for hours or days while retaining only the most recent window of history:

```bash
jcmd 12345 JFR.start name=service_ring settings=default disk=true duration=0s maxage=30m maxsize=256m dumponexit=true filename=/tmp/jfr-out/service-exit-%p-%t.jfr
```

This fits long-term monitoring:

- `duration=0s`: the recording **keeps running** until stopped or the JVM exits.
- `maxage=30m`: aims to retain roughly the most recent 30 minutes of data.
- `maxsize=256m`: caps retained data for this recording; when room is needed for new data, the oldest chunks are evicted.
- `settings=default`: lower-overhead config than `profile`, recommended for continuous recording.
- `dumponexit=true`: if the application shuts down cleanly while the recording is still running, JFR can export retained data.

**Do not infer:** "`maxage=30m` means the recording only runs for 30 minutes." The recording continues running until stopped; overly old data is evicted by retention policy. Nor should you infer "`maxsize=256m` means total JVM disk usage cannot exceed 256 MB": multiple recordings, active chunks being written, metadata, and **exported files** can make overall disk consumption larger.

### 3.3. In-Memory-Only Recording

```bash
jcmd 12345 JFR.start name=brief_memory disk=false duration=30s settings=default filename=/tmp/jfr-out/brief-memory.jfr
```

With `disk=false`, data is not continuously flushed to a disk repository; it is bounded by **in-memory buffers**, so older events may be lost. `maxage` and `maxsize` **have no disk-management effect** here, and `jcmd` docs require `disk=true` to use them. If the goal is a long "history window" to dump when an incident happens, you generally need `disk=true`.

## 4. The Repository Is a Temporary Directory, Not the Export File

When `disk=true`, the JVM writes JFR chunks into a **temporary repository**. By default, the repository typically lives under the OS temp directory. In container environments, the temp directory may sit on ephemeral storage or have tight size limits.

There are two ways—**differing in timing and syntax**—to choose the directory:

**Configure a running JVM** via `jcmd`, ideally before starting the recording you want to capture:

```bash
jcmd 12345 JFR.configure repositorypath=/tmp/jfr-repo
jcmd 12345 JFR.configure
```

Running without arguments displays the current JFR configuration. If you change `repositorypath` after the JVM has already written chunks, do not assume old chunks are automatically moved. Re-check the actual state of the running JVM.

**Configure at JVM startup**:

```bash
java -XX:FlightRecorderOptions=repository=/tmp/jfr-repo JfrLifecycleDemo
```

Note the **different option names**:

- `jcmd <PID> JFR.configure repositorypath=...`
- `java -XX:FlightRecorderOptions=repository=...`

Both specify where the JVM stores **temporary data**. Passing `filename=/tmp/jfr-out/...jfr` in `JFR.start` or `JFR.dump` specifies the **recording export destination**, not a parameter to move the repository.

### Directory Location and Access Permissions

In a Linux environment, prepare in advance:

```bash
mkdir -p /tmp/jfr-repo /tmp/jfr-out
```

These are only example directories for a learning environment. In real operations:

1. Both directories must **exist** and be writable by the **Java process's user**, not just the user running the `jcmd` terminal.
2. Paths are resolved in the **target JVM's filesystem**. If the JVM runs inside a container, `/tmp/jfr-out` inside the container does not automatically appear on the host; use an appropriate volume if files must survive container termination.
3. The repository and export directory can sit on separate storage to avoid space contention. A dump typically needs **dedicated space for the target file** while the repository still holds chunks.
4. Do not use temporary repository files as long-term evidence storage. By default, JFR may **delete repository chunks on JVM exit** when `preserve-repository=false`. Exported `.jfr` files must be managed, verified, and moved to approved storage.
5. Disk quotas, inodes, permissions, rotation, and cleanup schedules for exported files must be monitored at the system level. A single recording's `maxsize` does not replace those controls.

You can set `preserve-repository=true` via JFR configuration/flight recorder options when investigating temporary data. This is a flag to **retain repository chunks**; it does not guarantee producing a complete, valid `.jfr` file across every kind of shutdown—explicit exports remain the primary management method.

## 5. End-to-End Practice on a Java 17+ JVM

Use a simple program that runs long enough for `jcmd` operations. Save **`JfrLifecycleDemo.java`**:

```java
public final class JfrLifecycleDemo {
    public static void main(String[] args) throws InterruptedException {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("Shutdown hook executed")));

        long pid = ProcessHandle.current().pid();
        System.out.println("PID=" + pid);

        long checksum = 0;
        for (int second = 1; second <= 240; second++) {
            byte[] bytes = new byte[64 * 1024];
            bytes[0] = (byte) second;
            checksum += bytes[0];

            if (second % 15 == 0) {
                System.out.println("t=" + second + "s checksum=" + checksum);
            }
            Thread.sleep(1_000);
        }
        System.out.println("Finished normally");
    }
}
```

Compile and run in **terminal A**:

```bash
javac JfrLifecycleDemo.java
java JfrLifecycleDemo
```

The first line has the form `PID=12345`, where the PID is the JVM's actual OS PID and **varies across runs**. Every 15 seconds, the program prints a line `t=15s checksum=...`; the ellipsis here denotes the loop-dependent checksum value, not literal output. The program runs for about 240 seconds, or longer if the machine is busy or JFR operations take time.

In **terminal B**, replace `12345` with the real PID and prepare the directories per section 4.

### Step 1 — Identify the JVM and repository

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 JFR.configure repositorypath=/tmp/jfr-repo
jcmd 12345 JFR.configure
```

`jcmd -l` lists JVMs visible in the same attach environment, though it may not see JVMs running in another container/namespace. Ensure you have the right PID, right Java process, and access permissions.

### Step 2 — Start a rolling recording

```bash
jcmd 12345 JFR.start name=demo_ring settings=default disk=true maxage=2m maxsize=128m dumponexit=true filename=/tmp/jfr-out/demo-exit-%p-%t.jfr
jcmd 12345 JFR.check
```

This recording runs continuously by default because `duration` is omitted (equivalent to `0s`). The `maxsize=128m` limit is chosen to exceed the default chunk size of roughly `12M`. `JFR.check` verifies the running recording and confirms the name `demo_ring`.

### Step 3 — Manually export a snapshot while the recording keeps running

```bash
jcmd 12345 JFR.dump name=demo_ring filename=/tmp/jfr-out/snapshot-%p-%t.jfr
jcmd 12345 JFR.check
```

`JFR.dump` **writes a file without stopping the recording**. It fits cases where a spike or abnormal latency appears and you want to "lock in" the data window at that moment while the system keeps running.

To export only the most recent portion of retained data:

```bash
jcmd 12345 JFR.dump name=demo_ring filename=/tmp/jfr-out/last-30s-%p-%t.jfr maxage=30s
```

`maxage=30s` on **`JFR.dump`** bounds the time span **of that export**, without changing `maxage=2m` on the running recording. If less than 30 seconds of data remain (e.g., it only ran 10 seconds, or old chunks were evicted), the file contains only what is actually available.

### Step 4 — Inspect the exported file

Once the actual file exists at the path reported by `jcmd`, run the JDK's `jfr` tool **on a machine/namespace that can access the file**:

```bash
jfr summary /tmp/jfr-out/snapshot-12345-2026_10_29_17_00_00.jfr
```

The name above is an **illustrative path**, not a guaranteed generated filename; substitute the real filename. `jfr summary` reports recording time span, event counts/types, and other statistics. You can open the file in **JDK Mission Control** to inspect timelines, CPU, allocations, GC, and thread events enabled by the `.jfc` config.

If `JFR.dump` reports success but the file is missing on the host, check the **JVM's filesystem** and volume mounts before assuming JFR failed to write data.

### Step 5 — Verify dump-on-exit

While `demo_ring` is still running, let the JVM exit **via a normal shutdown path** (let the program finish or send an OS-appropriate graceful shutdown signal). After the process exits:

- Confirm a file matching `demo-exit-%p-%t.jfr` exists in `/tmp/jfr-out` as seen by the JVM.
- Run `jfr summary` on the **actual file** and note start/end timestamps and event counts.
- Compare the step 3 snapshot with the exit file; the new file contains only data still retained up to shutdown, possibly missing the beginning due to `maxage`/`maxsize`.

If instead you **explicitly run**:

```bash
jcmd 12345 JFR.stop name=demo_ring filename=/tmp/jfr-out/stopped-%p-%t.jfr
```

that is **an alternative branch**: `stop` ends and exports the recording immediately. When the JVM exits later, `demo_ring` is **no longer running** to export again via `dumponexit`. Do not both stop the recording and expect dump-on-exit for the same recording.

## 6. Launching the JVM with JFR Configured from the Start

When an application runs under a service manager, container, or deploy script, you can configure repository, retention, and dump-on-exit right at JVM creation. Example Linux command for the practice program:

```bash
java -XX:FlightRecorderOptions=repository=/tmp/jfr-repo -XX:StartFlightRecording=name=boot_ring,settings=default,disk=true,maxage=2m,maxsize=128m,dumponexit=true,filename=/tmp/jfr-out/boot-%p-%t.jfr JfrLifecycleDemo
```

Note the syntax:

- For `jcmd PID JFR.start`, `key=value` pairs are **space-separated**.
- For `-XX:StartFlightRecording=...`, `key=value` pairs are **comma-separated** within the same JVM option.
- For `-XX:FlightRecorderOptions=repository=...`, `repository` is the JVM option; do not copy `repositorypath` verbatim from `JFR.configure`.
- `-XX:StartFlightRecording` leaves `duration` unbounded by default. You can add `duration=2m` when a bounded recording is needed.
- Recording name `boot_ring` is simply an identifier for `jcmd PID JFR.check` / `JFR.dump name=boot_ring`.

Paths in the example are resolved in the filesystem where the Java process runs; create directories and grant permissions beforehand. In container orchestration, forcefully killing the JVM after too short a grace period may prevent dump-on-exit from finishing.

### Bounded startup example after warm-up

```bash
java -XX:StartFlightRecording=name=startup_triage,delay=20s,duration=60s,settings=profile,filename=/tmp/jfr-out/startup.jfr JfrLifecycleDemo
```

Here `delay=20s` waits 20 seconds after JVM launch before starting the recording; after **60 seconds of collection**, JFR stops and writes the file if it completes cleanly. Do not confuse `delay` with `duration`: total elapsed time from app launch until auto-stop is roughly 80 seconds under normal conditions.

## 7. `duration` and Retention: Why They Do Not Replace Each Other

Suppose a service runs for **8 hours** with:

```text
duration = 0s      # runs continuously until stop/exit
maxage   = 30m     # retains only recent history by age
maxsize  = 256m    # size cap retained on disk
disk     = true
```

At minute 10, data from startup is still present if `maxsize` has not been hit. At hour 8, retained history covers at most roughly the last 30 minutes—**or even less** if the event rate hits the `256m` cap first. Setting `maxage=30m` is not a guarantee of "always getting 30 minutes."

Simple back-of-the-envelope illustration, **not real JFR measurements**:

- If repository writes average `2 MB/minute`, 30 minutes needs around `60 MB`, so `maxage` may be the tighter constraint than `maxsize=256m`.
- If they average `20 MB/minute`, 30 minutes needs around `600 MB`, exceeding `256m`; the retained size-limited window could be only around **12–13 minutes** before accounting for chunk overhead.
- If `duration=5m`, the recording stops after 5 minutes even with `maxage=1h` and `maxsize=1g`. Those latter two limits do not extend the recording's lifetime.

JFR stores and evicts data in **chunks**; chunk boundaries, event rates, and multiple concurrent recordings make actual size/time diverge from linear math. Treat `maxsize` as a **retention budget for one recording**, not a byte-by-byte guarantee that the whole filesystem cannot exceed that limit. Provision enough free space for the repository, active chunks, exported files, and overhead.

### What happens when space is full and new events arrive?

With `disk=true`, JFR can evict **old chunks** to retain newer data when limits are exceeded. If an incident has not been exported yet, events in too-old windows can be permanently evicted. When an incident is detected, **dump immediately** to lock in evidence rather than waiting for retention to roll past; exported dump files need their own retention policy.

## 8. When Does Dump-on-Exit Work and When Does It Not?

`dumponexit=true` is a best-effort mechanism tied to the **JVM lifecycle**. It is helpful, not "insurance" for every failure.

| Situation | What Can You Expect? | How to Verify |
| --- | --- | --- |
| `main()` finishes normally while the recording is running | JVM executes shutdown; JFR has a chance to export the file | Check the `filename` file and run `jfr summary` |
| `System.exit(...)` under normal shutdown | Shutdown hooks get a chance to run; JFR has a chance to dump | Verify the file is complete; do not infer success from logs alone |
| Graceful stop from a service manager / `SIGTERM` on HotSpot Unix | JVM usually begins shutdown, **if** granted enough grace time | Check grace period, write permissions, logs, and file |
| `JFR.stop name=...` before JVM exit | Recording already stopped; dump-on-exit for that recording no longer applies | Read the file from `JFR.stop filename`; do not wait for an exit file |
| `duration` expired and the recording already auto-stopped | No recording remains running to dump on exit later | Verify the file written at auto-stop |
| `SIGKILL` / forced kill / forced container termination | No guaranteed shutdown path to run the dump | Trust only previously exported files; do not expect an exit dump |
| JVM crash / power loss / disk full / unwritable path | Dump-on-exit is **not guaranteed** | Check file, disk space, and I/O errors; data may be partial or missing |

**Do not equate** "the demo's shutdown hook printed" with "the `.jfr` file is definitely intact." The file must actually exist, open cleanly, and contain events for the target window.

In particular, in containers/Kubernetes, the temp directory may be wiped once the container disappears; you need durable volume storage and an adequate graceful termination period to retrieve the file. `dumponexit` does not turn a temporary repository into durable storage.

### Strategy for reducing risk of data loss

- For long-running systems: `disk=true`, finite `maxage`/`maxsize`, `settings=default`, and budgeted disk capacity.
- When an incident is spotted: call `JFR.dump` for an **immediate export** without stopping the recording.
- When ending cleanly: `JFR.stop name=... filename=...` to export and stop deliberately.
- When wanting end-of-life data: enable `dumponexit=true` upfront, point `filename` to a durable filesystem, and verify with `jfr summary` after shutdown.
- For crashes/forced kills: new file creation is not guaranteed; previously verified dumps are far more reliable evidence.

## 9. Managing Multiple Recordings and Scoping Exports

One JVM can host **multiple recordings**, such as a continuous rolling `service_ring` and a short `incident`. In that setup:

```bash
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=service_ring filename=/tmp/jfr-out/ring-snapshot.jfr
jcmd 12345 JFR.dump name=incident filename=/tmp/jfr-out/incident-snapshot.jfr
```

The `name` parameter selects the recording. Per `jcmd` documentation, omitting `name` on `JFR.dump` can export data from **all** recordings, which is undesirable when isolating a single source. Each recording has its own retention and export target; recording overhead and total storage still accumulate.

Operations are not interchangeable:

| Operation | Is the Recording Still Running? | Exported Data |
| --- | --- | --- |
| `JFR.check` | Unchanged | Creates no file; inspects status |
| `JFR.dump name=... filename=...` | **Yes**, if it was running | Snapshot of retained data at dump time |
| `JFR.dump ... maxage=10m` | **Yes** | Most recent slice within export limit |
| `JFR.stop name=... filename=...` | **No** | Writes retained data, then stops the recording |
| Recording hits `duration` with `filename` | **No** | Auto-stops and writes file per configuration |
| JVM shutdown with `dumponexit=true`, recording running | JVM exits | Attempts to write file to `filename` or generated name |

Do not confuse `JFR.configure` (JVM-wide JFR settings such as repository path) with `JFR.start` (per-recording options) or `JFR.dump` (options for **one export call**). Also do not confuse `JFR.dump` with `GC.heap_dump`: the two tools produce different formats and kinds of evidence.

## 10. Quick Checklist from Capture to Conclusion

Before recording:

1. **JDK/collector/PID:** `java -version`, `jcmd -l`, `jcmd PID VM.version`; use compatible `jcmd` and proper permissions.
2. **Goal:** capture a 1–5 minute incident or keep a 1–6 hour ring? Separate `duration` from `maxage`.
3. **Retention:** set both `maxage` and `maxsize` if you need to bound both **age** and **size**. Ensure `maxsize >= maxchunksize`.
4. **Directories:** repository and output sit on the JVM's filesystem, have write permissions, capacity, and appropriate volume mounts.
5. **Event config:** `default` for continuous, `profile` for short investigative bursts when deeper data is needed.
6. **On exit:** if `dumponexit` is enabled, verify exact destination file and service manager grace period.

During recording:

1. `jcmd PID JFR.check` to confirm the recording is running; do not rely solely on start having been issued.
2. When you need to preserve data around an incident, `JFR.dump` and record the **actual filename reported by the JVM**.
3. Watch repository usage, active recording count, free disk space, event rate spikes, and CPU/latency cost.
4. When retention settings change between runs, record timestamps and values to avoid invalid comparisons.

After recording:

1. `jfr summary file.jfr`; verify the file opens cleanly and has the right event types and time range.
2. Compare actual minutes of data present against `maxage`/`maxsize`; if shorter than expected, check event rate and chunk retention.
3. Open in JDK Mission Control when profile and timeline analysis is needed.
4. Store files per system policy since events can include thread names, methods, paths, arguments, or application info requiring access control.
5. Rotate/delete **exported files** with a dedicated storage policy; do not expect the repository's `maxsize` to clean them up.

## 11. Practical Scenarios and Choices

### Scenario A — Production service running all week

**Requirement:** when an incident occurs, retrieve roughly the last 30 minutes; do not let the repository grow unbounded.

Sample setup:

```bash
jcmd 12345 JFR.start name=prod_ring settings=default disk=true duration=0s maxage=30m maxsize=256m dumponexit=true filename=/tmp/jfr-out/prod-exit-%p-%t.jfr
```

Right when an incident occurs:

```bash
jcmd 12345 JFR.dump name=prod_ring filename=/tmp/jfr-out/prod-incident-%p-%t.jfr
```

**What must be verified:** "roughly 30 minutes" is a target, not a guarantee if `maxsize` is reached sooner. The export contains only surviving chunks.

### Scenario B — CPU spike right at startup

**Requirement:** skip 20 seconds of warm-up, record 1 minute in detail, then auto-export.

```bash
java -XX:StartFlightRecording=name=startup_spike,delay=20s,duration=60s,settings=profile,filename=/tmp/jfr-out/startup-spike.jfr JfrLifecycleDemo
```

Explanation: the recording starts after `delay=20s` and **runs for 60 seconds**. `maxage` and `maxsize` are not how you schedule a recording's start/end interval.

### Scenario C — Container frequently killed by timeouts

**Requirement:** avoid losing evidence when shutdown may be forced.

Operational solution: place the repository on a suitable volume, set retention limits, **dump proactively** before instance changes/reclaims whenever possible, check `jfr summary`, and still keep `dumponexit=true` as an extra fallback. Never claim dump-on-exit is guaranteed to run on `SIGKILL` or immediate container deletion.

### Scenario D — Disk full despite setting `maxsize=256m`

Questions to check:

- Are multiple recordings running concurrently?
- Were old exported `.jfr` files left behind?
- Are the repository and export path on the same partition/volume?
- Are temporary chunks, app data, or other logs consuming disk?
- Did an event-rate surge cause unusually rapid chunk writes/rotations?

**Right conclusion:** `maxsize` caps retained data for a single recording—it is **not a quota for the entire JVM, filesystem, or export directory**.

## 12. Common Mistakes

1. **Treating `maxage=30m` like `duration=30m`:** old data is evicted while the recording keeps running.
2. **Using `duration=0s` without disk retention limits:** long-running services can build substantial storage demand.
3. **Setting `maxsize` smaller than `maxchunksize`:** invalid configuration.
4. **Assuming `maxage`/`maxsize` caps exported `.jfr` files too:** output files must be managed separately.
5. **Setting `maxage`/`maxsize` with `disk=false`:** does not achieve repository retention; check docs/command output.
6. **Confusing `repository` with `filename`:** temporary chunks differ from the file handed to JMC.
7. **Using parameter name `repositorypath` inside `-XX:FlightRecorderOptions`:** the startup option name is `repository`.
8. **Putting commas between `jcmd JFR.start` parameters:** commas belong in the JVM flag `-XX:StartFlightRecording`; `jcmd` uses spaces.
9. **Running `JFR.dump` and assuming the recording stopped:** it continues running; verify with `JFR.check`.
10. **Calling `JFR.stop` before shutdown and expecting dump-on-exit:** no running recording remains to dump.
11. **Relying unconditionally on dump-on-exit during crashes/forced kills:** shutdown execution is not guaranteed.
12. **Not checking actual filenames with `%p`/`%t`:** easy to look at the wrong location or recording session.
13. **Not checking container/volume paths:** the file may sit inside the container instead of the `jcmd` caller's filesystem.
14. **Not saving timestamps/workload:** loses correlation with incident timing; you have a JFR file without knowing where to look.
15. **Skipping `jfr summary` verification:** a "Started recording" log proves start only, not a valid exported file.
16. **Running `profile` continuously without measuring overhead:** `profile` captures more data than `default`; weigh load and objectives.

## 13. Self-Check Exercises

**Question 1.** A recording runs for 12 hours with `duration=0s, maxage=1h, maxsize=512m, disk=true`. After 12 hours, can you dump all 12 hours of data?

**Answer:** You cannot expect that. Only chunks still retained under both limits exist; the history window is at most about one hour and may be shorter if `maxsize` was reached.

**Question 2.** A recording has `duration=2m` and `dumponexit=true`. The JVM stays alive for 5 hours. When the JVM exits after 5 hours, will the recording capture 5 hours of data?

**Answer:** No. The recording stops automatically after 2 minutes; dump-on-exit does not extend or restart the recording.

**Question 3.** After `JFR.dump name=prod_ring filename=...`, do you need to call `JFR.start` to keep the rolling history going?

**Answer:** No. `JFR.dump` does not stop the recording; verify with `JFR.check`.

**Question 4.** `dumponexit=true` is set, yet the JVM receives `SIGKILL`. Is a new file guaranteed?

**Answer:** No. Rely on earlier exports and verify their readability; do not depend on shutdown hooks.

**Question 5.** The JVM runs in a container; `jcmd` reports exporting `/tmp/jfr-out/test.jfr` succeeded, but the host cannot see it. Is JFR broken?

**Answer:** Not enough basis for that claim. Paths are resolved by the JVM/container; check namespaces, volume mounts, and the actual file inside the container.

**End-of-lesson practice:** Using `JfrLifecycleDemo`, create one bounded recording (`duration=30s`) and one continuous recording (`maxage=2m maxsize=128m`) in separate runs. For the continuous recording, take a `JFR.dump` while running, then let the JVM finish normally. Record the filenames, `jfr summary` numbers, and clearly explain the **stop point**, **retention window**, **temporary chunk location**, and **final export path**. You are done when you can predict and verify all five concepts without confusion.

## 14. Official Documentation

- [Oracle JDK 21 — `jcmd`: JFR.configure / JFR.start / JFR.dump / JFR.stop / JFR.check](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — `java`: `-XX:StartFlightRecording` and `-XX:FlightRecorderOptions`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle JDK 21 — `jfr`: `summary`, `print`, and file handling](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [Oracle JDK 21 — `jdk.jfr.Recording`: duration, retention, dump-on-exit](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- [Oracle — Flight Recorder Configurations: `default.jfc` and `profile.jfc`](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html).

**Rule to remember:** `duration` decides *when a recording stops*; `maxage`/`maxsize` decide *how much history stays retained*; `repository` decides *where temporary chunks live*; `JFR.dump` decides *when to export a copy*; and `dumponexit` is *a final export opportunity on normal JVM shutdown*, which must be verified against the actual file.

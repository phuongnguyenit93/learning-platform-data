# 14.10 Recovering Complete Chunks for Post-Incident Analysis

> **Context:** Java Flight Recorder (JFR) on HotSpot/JDK 17+ writes a recording in **chunks**. When the JVM terminates abruptly before exporting a final `.jfr` file, complete chunks may still remain in the **disk repository**. The `jfr assemble` tool can stitch them together for investigation. This recovers **data already written cleanly to disk**, not everything the JVM ever saw before dying.

## 1. Learning Outcomes and Scenario to Handle

After this lesson, you will be able to:

1. Explain the relationship between **JFR memory buffers**, **disk repository**, **complete chunks (`.jfr`)**, **in-progress chunks (`.part`)**, and the final exported recording file.
2. Determine when recovery is possible via `jfr assemble`, when you must use `jcmd JFR.dump`, and when no recoverable data remains.
3. Collect a **copy** of the post-incident repository without altering original evidence, selecting the exact chunk directory of **a single JVM**.
4. Assemble chunks, verify the recording with `jfr summary`, `jfr metadata`, and `jfr print`, and explain missing intervals.
5. Proactively configure storage to improve data survival on JVM crash/container kill, without equating that config with a zero-loss guarantee.

**Example scenario:** a Java service was recording JFR to investigate brief hangs. The container was suddenly `OOMKilled` or the JVM hit a fatal error, preventing creation of a complete `incident.jfr`. Several chunk files remain in the disk repository. The operator needs to gather **completed chunks**, inspect stack traces and events prior to failure, and correlate them with logs, metrics, and `hs_err_pid` if available.

Never start by renaming `.part` to `.jfr`, concatenating bytes manually, or restarting the service to "test" before preserving the old repository: those actions easily destroy or corrupt evidence.

## 2. Where Does JFR Actually Store Data?

### 2.1. Event Writing Flow

A simplified diagram:

```text
Java/JVM events
     |
     v
JFR thread-local / global memory buffers
     |
     | written/flushed to disk repository when recording uses disk=true
     v
JVM disk repository
     +-- complete chunks:    ... .jfr
     +-- in-progress chunks: ... .part
     |
     | normal dump/stop/exit or offline recovery
     v
Complete recording file: incident.jfr
     |
     +-- jfr summary / jfr print / jfr metadata
     +-- JDK Mission Control (JMC)
```

A **JFR chunk** contains the event data and metadata needed for a reader to parse that chunk; it is the unit that can be reassembled. In the disk repository, **completed** chunk files carry the `.jfr` extension; files currently being written typically carry the `.part` extension. Per JDK tool documentation, `jfr assemble` **orders completed chunks chronologically** and **ignores incomplete `.part` files**.

This establishes an important boundary:

- **Recoverable:** complete chunks that still exist, remain readable, and belong to the target recording/repository under investigation.
- **Not guaranteed recoverable:** events still sitting unflushed in JFR memory buffers, incomplete `.part` chunks, chunks evicted by retention, or repository data deleted or lost with the container/volume.
- **No final `.jfr` file does not mean all data is lost:** the repository may still hold usable chunks.

JFR is designed for low overhead and does not guarantee every event is retained under system overload, disk write failures, or JVM kills. Therefore, "assemble succeeded" confirms only that **the file is readable**, not that the recording covers every moment of the incident.

### 2.2. `disk=true` vs. `disk=false`

A recording with `disk=true` continuously flushes data from buffers to the **disk repository** per JFR policy; this is a key prerequisite for post-incident chunk recovery.

With `disk=false`, data remains primarily in the JVM's **memory buffers**; if the process dies before a dump, `jfr assemble` **lacks the disk chunks required for recovery**. `dumponexit=true` cannot substitute for data lost to `SIGKILL`, container kills, power loss, or severe JVM crashes.

| Situation | Appropriate Action |
| --- | --- |
| JVM **still running**, need recording right now | `jcmd <PID> JFR.dump ...` to export a snapshot without stopping the recording (if attach works). |
| JVM stopped **normally**, complete `.jfr` file exists | Use that file directly; verify with `jfr summary`. No `assemble` needed. |
| JVM died abruptly, repository still holds `.jfr` chunks | Copy the repository and run `jfr assemble` **offline** on the copy. |
| Only `.part` files exist, no complete `.jfr` chunks | `assemble` cannot recover incomplete chunks; do not rename or assume recoverability. |
| Recording ran with `disk=false`, JVM died without a dump | Cannot use `assemble` to reconstruct data lost in RAM. |
| Repository was deleted, lived on a lost ephemeral volume, or old chunks were evicted | Recovery must rely on other snapshots/backups; `jfr assemble` cannot recreate missing data. |

## 3. Preparing in Advance to Improve Recovery Chances

These are choices made **before an incident occurs**. In production, pick paths on storage with suitable capacity and retention, and review access permissions because JFR can contain stack traces, class/method names, paths, and sensitive runtime details.

### 3.1. Place the Repository in a Known Location

Example Linux startup command (directories must exist and the JVM account must have write permissions):

```bash
java \
  -XX:FlightRecorderOptions=repository=/var/lib/myapp/jfr-repository \
  -XX:StartFlightRecording=name=incident,disk=true,settings=default,maxage=30m,maxsize=256m,dumponexit=true,filename=/var/log/myapp/incident.jfr \
  -jar app.jar
```

Explanation:

- `-XX:FlightRecorderOptions=repository=...` specifies the **base directory for temporary JFR chunks**; JFR may create subdirectories per process or session.
- `-XX:StartFlightRecording=...` starts a recording at JVM launch.
- `disk=true` ensures the recording uses the disk repository; it is usually `true` by default, but stating it explicitly aids config reading and root-cause checks.
- `settings=default` uses the default JFR profile; swap in a verified `.jfc` if specialized events are needed.
- `maxage=30m`/`maxsize=256m` bound retained data in the repository; older chunks may be evicted. These numbers are **design examples only**; choose based on event rate, disk capacity, investigation window, and chunk size.
- `dumponexit=true` requests a dump when the JVM **shuts down through a normal exit path**; it is no guarantee against crashes or `SIGKILL`.
- `filename=/var/log/myapp/incident.jfr` is the **exported recording file** path, not the **repository** path. These are two locations with different roles.

In Kubernetes/containers, the default `repository` typically sits in JVM/OS temporary space. If a pod or filesystem is wiped on restart, chunks vanish immediately. For post-incident forensics, plan volumes and extraction workflows ahead of time; never assume `/tmp` survives pod recreation.

### 3.2. Checks Before an Incident Happens

While the JVM is alive, you can run:

```bash
jcmd -l
jcmd 12345 JFR.check name=incident verbose=true
jcmd 12345 JFR.configure
```

`12345` is an **illustrative PID**: replace it with the real PID from `jcmd -l` or OS tools. `jcmd` requires attach access to the JVM on the same machine/container with appropriate permissions; security policies or different namespaces can block attach.

On supporting JDKs, the command:

```bash
jcmd 12345 JFR.configure preserve-repository=true
```

tells JFR to keep files in the disk repository when the JVM exits **normally** instead of cleaning them up by default. **Must be configured while the process is alive**; you cannot invoke `JFR.configure` after the process has died. Preservation does not compensate for wiped/overwritten storage or incomplete chunks, nor does it turn `.part` into valid chunks.

Note two easily confused setting names:

- `repository=` in `-XX:FlightRecorderOptions` is a **JVM startup flag**.
- `repositorypath=` in `jcmd ... JFR.configure` is a **diagnostic command parameter while the JVM is alive**. Run `jcmd ... JFR.configure` to verify support and current state on the running JDK.

The repository directory serves as the recorder's working space; **do not turn it into a long-term backup archive**. Incident preservation policies should copy raw artifacts to a dedicated location with controlled permissions and retention.

## 4. Post-Incident Recovery Runbook: From Repository to `.jfr`

This is the main runbook. Commands below assume Linux/macOS with a Bash-compatible shell. Paths are illustrative; adjust to your deployment config and the **exact directory directly holding chunks** for the failed JVM.

### Step 1 — Preserve Evidence State and Confirm the JVM Has Stopped

Record the pre-crash PID, incident time (with time zone), JDK version, logs, container/pod ID, mount locations, and `disk`/`repository` settings. If the process is actually **still running**, prefer:

```bash
jcmd 12345 JFR.dump name=incident filename=/var/log/myapp/live-snapshot.jfr
```

This is safer than copying a directory while the recorder is actively mutating it. `JFR.dump` exports a file from the running recording without stopping it. If the process is already dead, `jcmd` cannot extract events from it.

### Step 2 — Locate the Exact Repository of a Single JVM

Suppose the base repository was configured at `/var/lib/myapp/jfr-repository`:

```bash
find /var/lib/myapp/jfr-repository -type f \
  \( -name '*.jfr' -o -name '*.part' \) -print
```

Select the **subdirectory containing the chunks of the specific process/session to recover**. A service with multiple processes, restarts, or recording sessions may leave distinct file groups; **do not mix chunks from different processes** just because they share the same extension.

If `.jfr` chunk files lie directly in the base repo directory, you can use that directory directly. If they lie inside a subdirectory, you must pass that **exact subdirectory** as input to `assemble`. When only `.part` files appear, explicitly document that no complete `.jfr` chunks exist rather than guessing.

### Step 3 — Copy to Preserve the Original

The example below assumes `/var/lib/myapp/jfr-repository/recording-001` is the **verified directory holding `.jfr` chunks**, and `/srv/incidents/incident-001` is the output location **outside the source repository**:

```bash
SOURCE_DIR=/var/lib/myapp/jfr-repository/recording-001
CASE_DIR=/srv/incidents/incident-001

mkdir -p "$CASE_DIR"
cp -a "$SOURCE_DIR" "$CASE_DIR/repository-copy"

find "$CASE_DIR/repository-copy" -maxdepth 1 -type f \
  \( -name '*.jfr' -o -name '*.part' \) -print
```

`cp -a` copies files while preserving much system metadata on Linux; target permissions and filesystem may affect metadata preservation. Record the copy timestamp, source, PID, JDK version, and storage policy so others can reproduce the investigation.

It is good practice to save checksums for the **copy**, for example:

```bash
find "$CASE_DIR/repository-copy" -maxdepth 1 -type f -name '*.jfr' \
  -exec sha256sum {} \;
```

Hashes prove copies remained unaltered across analysis passes. Do not edit chunk files, delete `.part` files, or rename files manually in the original. The output path must be **outside** the input directory so you do not accidentally feed the assembled file back into the source.

### Step 4 — Assemble Complete Chunks

Use the exact JDK command syntax:

```bash
jfr assemble "$CASE_DIR/repository-copy" "$CASE_DIR/recovered.jfr"
```

The two arguments are the **chunk directory** and the **new recording file path**. `jfr assemble` picks complete chunks, orders them chronologically, and writes them to the `.jfr` file. Per the JDK tool spec, incomplete `.part` files are **skipped**.

Do **not** do any of the following to "rescue" data:

- Rename `.part` to `.jfr` and treat it as a complete chunk.
- Concatenate files in name order with `cat`/`copy /b` without verifying they are valid JFR chunks from the same repository.
- Run `jfr assemble` on a parent directory accidentally holding multiple repositories from different processes or restarts.
- Start writing new JFR recordings into an uncopied repository, letting housekeeping or retention delete needed chunks.
- Delete chunk files mistaking them for "temp files" before saving a copy.

If the tool reports no chunks found, inaccessible path, or a corrupt chunk, **preserve the evidence copy intact** and inspect inputs. Never claim recovery succeeded when the command failed.

### Step 5 — Verify the Recovered File

```bash
jfr summary "$CASE_DIR/recovered.jfr"
jfr metadata "$CASE_DIR/recovered.jfr"
jfr print --events jdk.GarbageCollection,jdk.ExecutionSample \
  "$CASE_DIR/recovered.jfr"
```

- `jfr summary`: must parse cleanly, showing **version/chunk count/recording time span** plus counts per event type. These numbers help spot empty files, wrong processes, or mismatched incident windows.
- `jfr metadata`: confirms event schemas are readable, especially when the collecting JVM and analysis tool differ in version.
- `jfr print --events`: filters events relevant to your investigation. `jdk.GarbageCollection` or `jdk.ExecutionSample` may be absent if they were not enabled/captured during that window; empty output **does not mean `assemble` failed**.
- You can open `recovered.jfr` in **JDK Mission Control (JMC)** to inspect timelines, stack traces, GC events, locks, CPU, threads, and correlated charts.

**Check temporal coverage:** note start/end times of the recovered recording, incident timestamps from logs, chunk count, suspicious gaps, and target events. If the final chunk was lost or events remained in buffers, the final seconds right before the crash may **be missing**. A format-valid recovered file may still **not cover the final root cause** of the incident.

## 5. Why Can You Not "Recover Everything"?

### 5.1. Three Degrees of Data Loss

1. **Unflushed from buffers:** data remained in RAM when the JVM died; offline JFR tools have no material to recover it.
2. **In-progress `.part` chunk:** incomplete file, so `jfr assemble` skips it. Never rely on renaming extensions or patching a few bytes to claim a valid chunk was recovered.
3. **Completed chunk missing from disk:** may have been deleted by `maxage`/`maxsize`, shutdown cleanup, ephemeral filesystems, disk failure, or operational actions. `jfr assemble` cannot restore physically deleted files.

Additionally, events may have been **disabled**, filtered by threshold/sample rate, or dropped under heavy pressure in the first place. You cannot recover an event that was **never saved**, even if all chunks survive.

### 5.2. Understanding `maxage`, `maxsize`, and Chunk Rollover

`maxage`/`maxsize` are **on-disk retention policies for the recording**. Once thresholds are hit, the JVM may delete older chunks to make room; thus the remaining repo may reflect only the **most recent window**, not total uptime.

`-XX:FlightRecorderOptions=maxchunksize=...` tunes HotSpot's target/max chunk size; it does **not** mean every chunk is forced to that exact byte size, nor that a chunk is created every `maxage` minutes. A recording's `maxsize` must be compatible with chunk limits; pick thresholds large enough to retain a meaningful observation cycle.

If recovery close to an incident is important, plan **disk persistence** and retention policies upfront. This configuration raises your odds, yet the very final slice of data can still be lost.

## 6. Java 17+ Lab: Reconstructing a Recording from Complete Chunks

This lab uses a **valid recording**, deliberately splits it into multiple chunks with `jfr disassemble`, and reassembles them with `jfr assemble`. It tests syntax, format, and the assembly workflow; it **does not fully simulate** a `SIGKILL` crash or lost `.part` files.

### 6.1. Program Generating Many JFR Events

Create `JfrChunkLab.java`:

```java
import jdk.jfr.Enabled;
import jdk.jfr.Event;
import jdk.jfr.Name;

public class JfrChunkLab {
    @Name("lab.Checkpoint")
    @Enabled(true)
    public static class Checkpoint extends Event {
        int sequence;
        String phase;
    }

    public static void main(String[] args) {
        int markers = 350_000;

        for (int i = 0; i < markers; i++) {
            Checkpoint event = new Checkpoint();
            event.sequence = i;
            event.phase = "diagnostic";
            event.commit();
        }

        System.out.println("markers=" + markers);
    }
}
```

This is standard Java 17+ code using no internal APIs. `Checkpoint` is a custom JFR event; `@Name("lab.Checkpoint")` creates an easily recognizable type in `jfr summary`. `@Enabled(true)` enables the event type by default for recordings; JFR must be running before the loop emits events. Do not emit this event volume in production, as 350,000 events can cause noticeable overhead; this is strictly a short lab.

### 6.2. Compile and Capture the `.jfr` File

```bash
javac JfrChunkLab.java
java \
  -XX:FlightRecorderOptions=maxchunksize=1m \
  -XX:StartFlightRecording=filename=lab.jfr,dumponexit=true,settings=default \
  JfrChunkLab
```

**Stdout from the Java program**:

```text
markers=350000
```

Beyond the line above, the JVM may print `[jfr,startup]` messages about the recording. `maxchunksize=1m` is kept small for the lab to encourage multiple chunks; JFR may still write chunks larger than the configured target depending on runtime conditions. Chunk counts are not fixed across JDK versions or machines.

### 6.3. Disassemble and Reassemble

On Linux/macOS:

```bash
mkdir -p chunks
jfr summary lab.jfr
jfr disassemble --max-chunks 1 --output chunks lab.jfr
jfr assemble chunks recovered-lab.jfr
jfr summary recovered-lab.jfr
```

On Windows PowerShell, replace the `mkdir` command with:

```powershell
New-Item -ItemType Directory -Path .\chunks -Force
jfr disassemble --max-chunks 1 --output .\chunks .\lab.jfr
jfr assemble .\chunks .\recovered-lab.jfr
jfr summary .\recovered-lab.jfr
```

`jfr disassemble` creates smaller numbered files; with `--max-chunks 1`, each output file contains at most one chunk. If the recording has **only one chunk**, the tool may report **no need to disassemble**; generate a larger recording or more events and try again. Do not take that notice to mean the file is corrupt.

**Experimental results verified on OpenJDK 24:** with 350,000 custom events and the configuration above, the recording produced **3 chunks**; `jfr disassemble` produced 3 files, `jfr assemble` produced a file with **350,000 `lab.Checkpoint`** events, and the SHA-256 of the reassembled recording matched the pre-split file. That is a reference result from that single run, **not a guarantee** of identical chunk counts on JDK 17/21 or other environments.

Use:

```bash
jfr summary recovered-lab.jfr
```

to find event type `lab.Checkpoint` and check its event and chunk counts. If the event count differs from expectations, first verify the recording started before the loop ran, the event was enabled, sampling/retention settings, and JFR messages. **Calling `event.commit()` in code does not guarantee every event reaches the file under system pressure or data loss.**

### 6.4. How Does the Lab Relate to Post-Crash Data Recovery?

In the lab, `jfr disassemble` intentionally produces complete `.jfr` files from a valid recording. After a real crash, surviving `.jfr` chunks in the disk repository serve as the **input** to the exact same `jfr assemble` tool—you do not need to have run `disassemble` beforehand.

Do not invert the workflow into "you must have an intact recording file before recovering": `disassemble` is only for learning/testing or splitting an **already-readable recording**. After a crash, if the target file was never dumped, the recovery source can be the **repository holding complete chunks**.

## 7. When a `.jfr` File Exists but Shows Signs of Corruption

First **copy the broken file** and preserve the original. Then run:

```bash
jfr summary suspicious.jfr
jfr metadata suspicious.jfr
```

If both read successfully, the file may still hold valid chunks; proceed to inspect time ranges and event types. If the file is large and **readable**, `jfr disassemble --max-chunks 1` can split chunks individually to isolate usable portions for analysis. If only one chunk segment is damaged, you can try assembling **verified valid chunks** in a new directory; always document the excluded time span.

Conversely, if `jfr disassemble` also fails to parse, **there is no guarantee** JDK tools can rescue a binary file truncated mid-stream or corrupted. You may need other snapshots/backups or specialized forensic tools, and should never promise to turn every `.part` or corrupt file into a complete recording.

## 8. Diagnosing Errors During Recovery

| Symptom | Interpretation | Action |
| --- | --- | --- |
| `jfr assemble` finds no chunks | Wrong directory, repo cleaned up, only `.part` files remain, or not a disk recording | Confirm `disk=true` pre-incident, inspect directory tree/volumes/backups, pick exact leaf directory. |
| Multiple PID/recording directories exist | Multiple JVMs or recording sessions shared the same base repo | Identify PID, timestamps, and file groups; process **each repository separately**. |
| Multiple `.part` files exist but zero `.jfr` files | No completed chunks remain to assemble | Preserve existing files; do not rename extensions or claim "recovery succeeded." |
| `jfr summary recovered.jfr` fails to read | Missing/corrupt output, wrong input types, or tool compatibility mismatch | Read actual error, verify input list, try a JDK tool version matching the recording JVM. |
| File reads cleanly yet target events are missing | Event disabled, threshold/sampling, mismatched recording window, lost chunk | Compare `.jfc`, logs, `jfr summary`, timestamps; do not blame `assemble` for every gap. |
| No data immediately before crash | Unflushed buffers, skipped `.part`, retention/gaps | Clearly report uncovered time span; cross-check `hs_err_pid`, GC logs, app logs, and OS metrics. |
| `jcmd JFR.dump` reports attach denied | Permissions, process namespace, or environment policy | Use proper permissions/context **while the JVM is alive**; do not run `jcmd` after PID dies. |
| Pod restart wiped old `/tmp` | Ephemeral storage / lifecycle cleanup | Check volumes/snapshots/backups; design durable storage and pre-restart evidence extraction next time. |
| Filenames ordered differently from timestamps | Renaming, copying, clock skew, or tool-generated names | Let `jfr assemble` sort chunks by metadata; do not concatenate by filename without verification. |
| Recovered file duration is shorter than uptime | Recording ran only for a window, `maxage`/`maxsize` evicted old chunks, or chunks missing | Report the exact evidenced window instead of calling it the entire JVM history. |

### Do Not Confuse the Tools

| Command | Input / Output | When to Use |
| --- | --- | --- |
| `jcmd PID JFR.dump ...` | **Live** JVM → `.jfr` snapshot | Capture data before stop/restart; not an offline tool. |
| `jcmd PID JFR.stop ...` | **Live** JVM → stops recording and optionally writes `.jfr` | End an active recording. |
| `jfr assemble REPO OUT.jfr` | Directory of **complete chunks** → `.jfr` recording | Offline recovery when only chunks remain after an incident. |
| `jfr disassemble FILE.jfr` | **Readable** recording → chunk/segment files | Labs, splitting large files, isolating valid segments. |
| `jfr summary FILE.jfr` | `.jfr` recording → chunk count, event counts, summary metadata | Validate and assess results. |
| `jfr print --events ... FILE.jfr` | `.jfr` recording → text event details | Inspect stacks/timestamps/fields after validating the file. |
| JMC | `.jfr` recording → timeline, charts, correlations | Investigate incidents from surviving events. |

## 9. Rules for Preservation, Completeness, and Privacy

**Preserve evidence:** record original paths, PID/host/container IDs, collection timestamps, and JDK build; make a separate copy before working on it. With multiple files, checksum each `.jfr` file to verify nothing changed between steps. Keep `.part` files in the raw archive even though `assemble` cannot use them, as they are still evidence of mid-write state at failure time.

**Do not equate "file parses" with "incident fully captured":** `jfr summary` validates structure and event types; investigation still requires time spans, event settings, buffer/retention behavior, and external JVM data. For example, if GC logs/OS report OOM at 10:00:05 yet the recovered recording ends at 10:00:01, the accurate conclusion is **JFR recovered up to 10:00:01**—never claim there was no GC or OOM afterward.

**Read timestamps in the right time zone:** JFR tools may display UTC or local time depending on command/version. When correlating application, container, tracing, and OS logs, normalize to a single time standard and state units (ms/ns) clearly to avoid false causal inferences.

**Control access:** JFR can hold thread, class, method, and frame names, paths, system/environment info, and custom event payloads; never upload to public services or attach to uncontrolled tickets without checking data policies. Treat recovered files as sensitive system diagnostic artifacts.

**Match environments:** run `jfr` from a JDK compatible with the recording version; use `jfr metadata` to inspect actual schemas. If an older tool cannot parse a newer recording, upgrade the analysis JDK rather than patching bytes.

## 10. Practical Operations Checklist

- [ ] Determine whether the **JVM is dead or still running**; if alive, prefer `jcmd JFR.dump` with proper permissions.
- [ ] Locate the exact **disk repository** and chunk group for **one JVM/session**; confirm at least one complete `.jfr` chunk exists.
- [ ] Preserve the original, copy the entire relevant directory including `.part` files, and record metadata and checksums.
- [ ] Place **output outside the input repository**, and run `jfr assemble` on the copy.
- [ ] Run `jfr summary` and `jfr metadata` to verify the file parses cleanly, checking chunk count, start/end times, and event counts.
- [ ] Open in JMC or use `jfr print` to analyze; align timelines with logs, GC, container/OS metrics, and crash artifacts.
- [ ] Explicitly report **surviving data, missing data, and what cannot be inferred** (buffers, `.part`, retention, event settings).
- [ ] For next time, verify `disk=true`, repository path, volume durability, permissions, retention, and pre-restart snapshot procedures.

**Conclusion:** after an incident, `jfr assemble` is the tool for **completed JFR chunks still on disk**. It can rescue useful history even when a final recording file was never dumped, yet it cannot recreate events lost in RAM, incomplete `.part` chunks, or deleted chunks. Successful recovery must be paired with **content verification and explicit disclosure of time-range limits**.

## References

- [Oracle JDK 21 — `jfr` command: `assemble`, `disassemble`, `summary`, `metadata`, `print`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — `jcmd`: JFR.configure, JFR.start, JFR.check, JFR.dump](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — Java launcher: `-XX:StartFlightRecording`, `-XX:FlightRecorderOptions`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Dev.java — Configuring the JDK Flight Recorder, disk/repository/chunks](https://dev.java/learn/jvm/jfr/configure/)
- [Dev.java — The JFR command-line tool](https://dev.java/learn/jvm/jfr/tools/)
- [JDK 24 API — `jdk.jfr.Recording`, `setToDisk`, `dump`, `setMaxAge`, `setMaxSize`](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Recording.html)

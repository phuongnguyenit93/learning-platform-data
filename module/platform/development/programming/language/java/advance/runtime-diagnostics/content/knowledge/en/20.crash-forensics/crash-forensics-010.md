# 20.10 Building a Minimal Evidence Bundle and Reproducer for Further Investigation

## 1. Goal: Handing Over an Incident So Someone Else Can Still Investigate It

After a JVM incident, the person taking over usually lacks the exact terminal, login session, data, and memory of whoever witnessed it. A single line like “Java crashed around 10 o'clock” or an isolated `hs_err_pid*.log` file is rarely enough. To enable continued investigation, you need a **minimal evidence bundle with clear provenance and timestamps**, paired with a **safe reproduction recipe**.

A solid bundle answers six questions:

1. **What happened?** Observed symptoms, impact, and the difference between expected and actual behavior.
2. **What did it happen to?** JDK vendor/build, JVM flags, application/commit, OS, CPU architecture, container, cgroups, and resources.
3. **When did it happen?** Timeline, timezone, PID, JVM start time and failure time, and correlation with deployments/load/GC.
4. **What raw evidence remains?** Fatal error logs, stderr/stdout, heap/core dumps, JFR, GC logs, exit status, and OS events **depending on incident type**.
5. **How to retry/reproduce?** Initial conditions, sanitized test data, commands, trigger steps, trial count, results, and control runs.
6. **What comes next?** Hypotheses, supporting/contradicting facts, evidence gaps, owner, and data access scope.

“**Minimal**” does not mean “as few files as possible at all costs,” but rather **enough data for another engineer to distinguish the main hypotheses without exposing unnecessary data**. Sending only a screenshot when timelines, logs, and diagnostic files exist rarely meets this goal.

Scope: Java 17+ on HotSpot with JDK 21 command examples, focusing on **crashes and post-failure investigation**; never use forced crash reproduction on production systems. On other JVMs, operating systems, or container environments, core creation/storage and collection tools may differ.

## 2. Before Collecting: Classify the Phenomenon Properly

Not every case of “Java app died” is a **JVM fatal crash**. The incident type dictates which artifacts can plausibly exist.

| Phenomenon type | Common symptoms | Priority evidence | What must not be assumed |
| --- | --- | --- | --- |
| **Unhandled Java exception** | Stack trace `Exception in thread "main"`; process may exit if no non-daemon threads remain | App stderr/stdout, logs, exception class/message/stack, exit status, triggering input/path | That `hs_err_pid*.log` or a JVM core dump exists |
| **HotSpot fatal error / native crash** | `SIGSEGV`, `SIGBUS`, `EXCEPTION_ACCESS_VIOLATION`, VM fatal error notice | `hs_err_pid*.log`, core/crash dump if present, native library/build, OS events | That the single “Problematic frame” already confirms root cause |
| **`java.lang.OutOfMemoryError`** | `Java heap space`, `Metaspace`, `Direct buffer memory`, etc. | Message/stack, heap/GC metrics, `.hprof` if enabled and written cleanly, memory config | That every OOME is a heap leak; that a heap dump always exists |
| **OS/container OOM kill** | Process vanishes; orchestrator may log `OOMKilled`, host has OOM killer events | Kernel/cgroup/orchestrator events, limits/usage, restart history, exit status | That the JVM had time to write `hs_err`, heap dump, or shutdown JFR |
| **Forced termination** | `SIGKILL`, container killed, watchdog/timeout | Service manager, audit/orchestrator, exit reason/timeline | That exit code 137 **alone** proves an OOM kill |
| **Hang/deadlock, not crashed yet** | Process stays alive, requests time out; threads make no progress | Multi-point thread dumps, JFR, metrics, queues, lock info | That a fatal error log exists; that you should kill immediately “to get evidence” |
| **Intentional JVM/process exit** | `System.exit`, shutdown from deploy or health policy | App shutdown logs, exit status, deploy/orchestration timeline | That this is definitely a HotSpot bug |

**Triage rule:** if `hs_err` is absent, that does not prove “not a JVM crash,” since insufficient permissions/disk or an abrupt kill can prevent it. Conversely, having a Java exception stack **does not justify assuming** HotSpot itself is broken. Always check independent evidence.

### Key differences

- **Fatal error log** reports HotSpot's state at an unrecoverable error; it is not the same as a Java exception stack trace.
- **Core dump** usually holds OS/native-level process memory, can be huge, and may contain passwords, tokens, or personal data in memory.
- **HPROF heap dump** describes the Java object graph / heap; useful for some OOMEs/leaks, yet does not fully describe native heap, stacks, kernel state, or all crash causes.
- **JFR** recounts JVM events within its retained window; useful when enabled beforehand. An unexpected crash or kill **does not guarantee** an exit-dump recording is produced.
- **App/OS logs** can confirm requests, deploys, resource limits, signals, and symptom onset; sometimes they matter even more than giant binary files.

## 3. Order of Actions Right When an Incident Occurs

In a real incident, priority actions must balance **service recovery** and **preserving volatile evidence**. Follow your organization's incident and authorization procedures; never leave a broken service down solely to gather data.

1. **Mark timestamps:** record UTC time (ISO 8601), displayed timezone, host/pod/instance, service name, deployed version, and recorder. If host clocks drift, record known skew.
2. **Verify whether the process is still alive:** if alive, collect low-risk, targeted snapshots; if dead, never try `jcmd` on the old PID or assume a new process with the same PID is the failed one.
3. **Preserve artifacts about to vanish:** buffered logs, files in containers about to be deleted, JFR within retention, kernel/orchestrator events, `hs_err`, and core locations. Prefer controlled copying **before** restart/cleanup when feasible.
4. **Capture relevant operational state:** resource limits, GC/JIT flags, CPU/memory pressure, queues, traffic, deploys/restarts, and config changes; note how each figure was obtained.
5. **Never overwrite originals:** store original copies in secure storage and compute checksums when feasible; perform redaction on **working copies**, never mutating originals.
6. **Recover and monitor:** after securing needed evidence per the runbook, restore the service, verify health, and record recovery time. A restart can wipe data, so order of actions must be recorded in the timeline.
7. **Package for the next person:** deliver a one-page summary, manifest, timeline, relevant files, and a reproduction recipe; explicitly list what **could not be collected**.

If capturing a core or heap dump could exhaust disk, worsen pauses, or expose sensitive data, **do not force capture just to “check off a list.”** Record why the artifact is missing and how to collect it next time.

## 4. What Parts Make Up a “Minimal Bundle”?

At minimum, include three groups: **documentation + facts + reproduction**. Example layout:

```text
INC-LAB-001/
├── README.md                 # Summary: observations and questions to answer
├── manifest.json             # Host/JDK/build/flags/limits/timestamps/sources
├── timeline.csv              # Deploy, request, GC, error, restart, and capture milestones
├── reproduction.md           # Preconditions + execution steps + verification oracle
├── artifacts/
│   ├── stdout.log            # Logs reviewed for sensitivity
│   ├── stderr.log
│   ├── exit-code.txt
│   ├── app.log               # Only if present
│   ├── gc.log                # Only if present
│   ├── hs_err_pid12345.log   # ONLY if a fatal log actually appeared
│   ├── incident.jfr          # ONLY if a valid recording exists
│   ├── java_pid12345.hprof   # ONLY if applicable and collected
│   └── core                  # ONLY if authorized/collected
└── SHA256SUMS.txt            # Hashes of the exact files actually packaged
```

This directory tree is an **example structure**, not implying every incident must contain all files. For a straightforward Java exception, `README.md`, `manifest.json`, `reproduction.md`, stderr, command, and exit status are usually enough for handover. For a complex fatal JVM crash, `hs_err`/core/native libraries take center stage.

Every file in the bundle should be classified:

- **Required:** essential for the recipient to understand the failure, such as build version and error message.
- **Conditional:** present only when the error type and settings support it, such as HPROF or JFR.
- **Missing with reason:** would have been useful yet was lost or uncollectable; state why rather than silently omitting it.
- **Restricted:** contains secrets or sensitive data; restrict access strictly to those who need it.

## 5. Incident README: A Structured One-Pager

A summary should be far clearer than “hit a JVM error, please check.” **Hypothetical lab example**:

> **INC-LAB-001, status:** root cause not yet concluded.  
> **Symptom:** running `IncidentReproDemo range-error` causes the main thread to throw `IllegalArgumentException` with message `quota out of range: 150`, and the process returns a nonzero exit status.  
> **Expected:** valid input `valid` produces `quota=25` and exits successfully; out-of-range input is handled per the application contract rather than crashing the main thread.  
> **Environment:** JDK 21 (record actual vendor/update in manifest), local Linux, single JVM, no container.  
> **Reproduction:** per `reproduction.md`; repeated 3/3 times with the same build and input.  
> **Evidence:** stdout/stderr, exit code, test source, JDK version, SHA-256.  
> **Not present:** `hs_err`/core are not expected in this Java exception scenario.  
> **Next investigation:** inspect validation and error handling at the input boundary; compare against real-environment conditions.

Never write “**root cause confirmed**” merely because an exception was reproduced; reproduction confirms **a path that produces the symptom**, whereas production root cause may involve concurrency, data, configuration, and event sequences not yet verified.

### Key summary fields

| Field | Level of detail needed |
| --- | --- |
| Incident ID and contact | Consistent ID; point of contact and access scope |
| Symptoms and impact | Observable facts, user/request scope, duration |
| Expected vs. actual | Verifiable expected behavior and exact deviation |
| Confidence level | Observed, suspected, confirmed-by-test; avoid overclaiming |
| Environment | Version, OS, architecture, container, build, JVM flags |
| Time window | UTC and timezone, linked to logs/JFR |
| Reproduction steps | Command/script, sanitized input, preconditions, success rate |
| Missing evidence | Absent items, why missing, how to capture next time |
| Next actions | Priority hypotheses, owner, discriminating experiments |

## 6. The Manifest Is a Context Record, Not an Indiscriminate Dump of Every Env Var

A `manifest.json` has a simple schema so both humans and machines can read it on handover. Below is an **example using hypothetical lab data**, not metrics from a real service:

```json
{
  "incident_id": "INC-LAB-001",
  "classification": "uncaught-java-exception",
  "observed_at_utc": "2026-10-29T09:20:00Z",
  "timezone_of_reporter": "Asia/Ho_Chi_Minh",
  "service": "incident-repro-lab",
  "environment": "local-lab",
  "jdk": {
    "major": 21,
    "vendor": "verify-from-java-version",
    "full_build": "record-the-actual-java-version-output"
  },
  "application": {
    "source_file": "IncidentReproDemo.java",
    "build_revision": "record-the-exact-commit-or-artifact-hash",
    "scenario": "range-error"
  },
  "runtime": {
    "os": "record-os-and-architecture",
    "pid": "record-pid-from-the-failed-run",
    "jvm_flags": "record-relevant-flags-without-secrets"
  },
  "symptom": {
    "error_class": "java.lang.IllegalArgumentException",
    "error_message": "quota out of range: 150",
    "process_exit": "nonzero"
  },
  "files": [
    "artifacts/stdout.log",
    "artifacts/stderr.log",
    "artifacts/exit-code.txt"
  ],
  "missing_expected": [],
  "sensitive_data_reviewed": true
}
```

Descriptive placeholders like `record-the-actual-java-version-output` emphasize the **rule against fabricating metadata**: in real incidents, fill in **measured** values; if uncollected, store `null` and explain in `README`. Never guess vendor, version, commit, or PID. You may use your organization's own JSON schema as long as the recipient understands every field.

**Fields worth recording in production incidents:** JDK distribution/build/update, CPU architecture, host/pod/container name and restart count, base image, OS/kernel, deployment ID/commit, process start time and uptime, `-Xms/-Xmx`, collector, heap/native/cgroup limits, disk status, enabled features/operations, and traffic/queue depth at failure time. Record both **config source and timestamp**; never dump raw environment variables because they may contain secrets.

## 7. Recording the Timeline: Time Is Evidence, Not Decoration

A timeline separates **recorded events** from **hypotheses**. Hypothetical template:

```csv
timestamp_utc,source,event,evidence,confidence
2026-10-29T09:19:30Z,deployment,build activated,deploy-log,observed
2026-10-29T09:19:55Z,application,request batch began,app-log,observed
2026-10-29T09:20:00Z,application,exception printed,stderr.log,observed
2026-10-29T09:20:01Z,supervisor,process exited,exit-record,observed
2026-10-29T09:20:15Z,operator,incident acknowledged,incident-log,observed
```

Never put a hypothesis like “GC caused the crash” in the `event` column as fact. Record “GC pause reported in GC log”; the assessment “may have a causal relationship” belongs in the analysis section with its own confidence rating.

Timestamps can come from JVM clocks, OS, collectors, APM, and load balancers:

- Keep ISO 8601 with **offset/timezone**; never mix `09:20` UTC with `09:20` Vietnam time.
- Record **start and end** of durational events (GC pauses, requests) instead of a single point.
- When host clocks drift, record estimated skew and sync source; dashboard display order is not guaranteed to be physical order.
- After a restart, PIDs can be reused; pair **PID + process start time + instance/container ID** to tell runs apart.
- JFR has a retention window; having data after time T does not prove it retained events prior to T.

## 8. Preparing Ahead: Configure So Evidence Isn't Lost Next Time

If you only start preparing **after** the JVM has died, many artifacts cannot be created retroactively. On HotSpot, consider pre-configuring flags aligned with risk, disk capacity, and system policies.

Examples of **individual startup configuration choices** (Linux, paths are illustrative):

```bash
# Fatal VM error: file at a writable path.
java -XX:ErrorFile=/var/log/java/hs_err_pid%p.log -jar service.jar

# On OutOfMemoryError: heap dump if space suffices and JVM can write.
java -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/var/log/java/ -jar service.jar

# GC + safepoint log with timestamps and bounded log rotation.
java -Xlog:gc*,safepoint:file=/var/log/java/gc.log:time,uptime,level,tags:filecount=5,filesize=20m \
     -jar service.jar
```

These are **separate/alternative syntax examples**, not three commands to launch simultaneously for one service; in operations, combine needed options into **one** tested launch configuration. Beforehand, create directories, grant permissions to the **JVM user**, and set storage quotas and retention; paths must exist inside the JVM/container filesystem.

What to understand:

- `-XX:ErrorFile=...` picks the fatal error log location. Not every Java exception creates this file. If the path is unwritable, the JVM may try a fallback such as the OS temp directory.
- `-XX:+HeapDumpOnOutOfMemoryError` with `-XX:HeapDumpPath=...` helps in certain OOME cases. `.hprof` files can be huge and hold sensitive data; lack of disk/permissions or certain error types can prevent the dump from appearing.
- `-Xlog` preserves timestamped GC/safepoint evidence; rotation can overwrite earlier phases as logs wrap. During long incidents, ensure enough window remains for analysis.
- Core dumps are governed by **OS/runtime policy**, not Java flags alone. Many container/service-manager environments impose `ulimit`, kernel `core_pattern`, `systemd-coredump`, disk quotas, or other capture rules.
- In production, changing JVM flags may require a restart and alter overhead; follow approved deployment procedures.

### Capturing JFR with a rolling history window

When you need a pre-incident timeline and accept the storage cost:

```bash
java -XX:StartFlightRecording=name=service_ring,settings=default,disk=true,maxage=30m,maxsize=256m,dumponexit=true,filename=/var/log/java/exit-%p-%t.jfr -jar service.jar
```

- `maxage/maxsize` bound data **retained in the repository**, not necessarily the entire exported `.jfr` file.
- `dumponexit=true` can dump when the JVM **shuts down normally while the recording is active**. With `SIGKILL`, power loss, or crashes bypassing normal shutdown, there is **no guarantee** the exit-dump file will appear.
- While the JVM is **alive**, you can call `JFR.dump` to persist data before the incident ages out of retention; you cannot call it after the process has died.

Test settings before an incident: verify disk capacity, enabled events, collision-free naming, container path placement, `jfr summary` readability, retention policy, and access controls.

## 9. While the JVM Is Still Alive: Selective Collection Commands

With a live HotSpot JVM and a **verified PID 12345**, in an authorized environment:

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.uptime
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.info
jcmd 12345 Thread.print -l
```

These are **live state-reading commands**, suitable when investigating hangs or abnormal latency while the process is still running. `jcmd` requires JDK tools, attach permissions, and matching namespaces. Some commands incur significant cost with many threads; do not take snapshots too frequently.

To export into separate files in a dedicated, permission-restricted evidence directory:

```bash
jcmd 12345 VM.version > vm-version.txt
jcmd 12345 VM.command_line > vm-command-line.txt
jcmd 12345 VM.flags > vm-flags.txt
jcmd 12345 Thread.print -l > threads-T0.txt
```

Ensure collected files carry timestamps in the manifest/filenames and log the exact commands run. **`VM.command_line` or `VM.info` can expose tokens/URIs/configs**, so restrict access and redact before sharing.

If the JVM has an active JFR recording named `service_ring`:

```bash
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=service_ring filename=/var/log/java/on-incident-%p-%t.jfr
```

`JFR.dump` exports retained data **without stopping** the recording. The file is written to a path resolved by the **target JVM**, especially inside containers. Only pass `name=service_ring` if `JFR.check` actually lists that name; never guess that every JVM has JFR running.

**Not default “minimal” actions:** `jcmd PID GC.heap_dump ...`, `GC.class_histogram`, or forcing a Full GC. Those commands can cause pauses and heavy I/O that perturb the very phenomenon under study. Use them only when required by a hypothesis and with approval and capacity.

If the JVM **has already died**, stop here: `jcmd` commands cannot revive a dead process. Switch to `hs_err`, cores, app/OS logs, exported JFRs, OOM records, and saved build/environment metadata.

## 10. Choosing the Right Evidence by Symptom

### 10.1. Fatal error log: `hs_err_pid*.log`

For a fatal HotSpot error, check the configured `-XX:ErrorFile` location or working directory / temp fallback. Read in a productive order:

1. **Header:** signal/native exception type, JDK vendor/build, VM, OS/architecture.
2. **Problematic frame:** native/VM/JIT frame where the crash was detected; distinguish `C` (native), `V` (VM code), and `J` (compiled Java) in the relevant format.
3. **Current thread / native & Java frames:** which thread reported the fault, stack context, and JNI/JNA/native library call origins.
4. **Process/VM info:** loaded libraries, `VM Arguments`, heap, thread stack, address/memory map, and environment.
5. **Before/after in timeline:** deploys, native library updates, GC activity, resource pressure, and container events.

**Never conclude** “library X is definitely the root cause” just because it appears in the problematic frame. It may be where the memory access fault **surfaced**, whereas memory corruption occurred earlier. You need cores, symbols/builds, a reproducer, and hypothesis testing.

The fatal log may be **incomplete** if the failure was severe or file writing failed; never taint evidence by inventing guessed missing content.

### 10.2. Core/crash dump: when native state investigation is needed

A core dump is a massive artifact—collect it only when needed. It can contain **the entire memory of the process**: authentication secrets, user data, heap contents, and native buffers. Enforce strict permissions, encryption/retention per policy, and mark sensitive data.

When handing a core to an analyst, you generally also need the **exact** executable/runtime build, native libraries, debug symbols if available, OS/architecture, container context, and capture timestamp. Never substitute a “close” JDK and treat the backtrace as exact proof. On Linux, cores may be held by `systemd-coredump` instead of creating a `core` file in the working directory; check configuration and access permissions with administrators.

Example **solely to check metadata presence** on a Linux host with `systemd-coredump`, when authorized:

```bash
coredumpctl list
coredumpctl info
```

Not every OS has `coredumpctl`; outputs differ between host and containers. Never run forced core-generation commands in production just to fill out a checklist.

### 10.3. OOME: do not confuse memory regions

`OutOfMemoryError` can arise from `Java heap space`, `Metaspace`, native allocations, thread creation, or direct buffers. A heap dump helps answer which Java objects occupy the heap, yet is **insufficient** to explain all native OOMs or OS kills. If the app is no longer alive, `jcmd` cannot generate a retroactive heap dump.

Collect additionally if available: `-Xmx`, cgroup limits, GC logs/post-GC used, metaspace/NMT if enabled, native allocation metrics, thread counts, container OOM events, history, and input/batch sizes. When an `.hprof` exists, verify path, size, readability, and permissions before transferring; never email sensitive files over public channels.

### 10.4. OS kill: look for evidence outside the JVM

If the container reported `OOMKilled` or exited with status `137`, cross-check **orchestrator events, kernel/cgroup metrics, limits/peak usage, and restart history**. Status 137 commonly aligns with `SIGKILL` under shell/container conventions, yet **does not prove** the OOM killer: an operator's `kill -9` or a policy timeout can produce the exact same exit code.

Do not treat `hs_err` as a mandatory requirement for an OS kill; the JVM may have had no chance to create a fatal log, heap dump, or JFR exit dump.

### 10.5. Hang: multiple stack snapshots and progress

A single thread dump shows state at one instant, not whether threads are **making progress** or stuck long-term. If authorized and the process is alive, take several intentionally spaced snapshots, record timestamps, and compare stacks/locks/queues alongside request metrics. Do not infer “deadlock” simply because many threads are `WAITING`: normal thread pools often wait for work.

## 11. Reproducer: What Is Enough for Someone Who Wasn't There?

A description like “crashes occasionally under heavy load” is not a complete recipe. A **reproducer** should include:

| Component | What must be answered clearly |
| --- | --- |
| **Preconditions** | JDK vendor/build, OS/arch, flags, memory/CPU limits, sanitized input dataset, dependency configs |
| **Exact artifact** | Commit or SHA-256 of JAR/container image/native library; source and build instructions if needed |
| **Starting state** | Fresh process or warmed service; caches, DB state, queue/traffic, uptime since start |
| **Trigger** | Exact command, request pattern, endpoint/case, sequence, concurrency, and duration |
| **Oracle** | Expected vs. actual signals: exception class/message, exit code, `hs_err`, signals, timeline |
| **Frequency** | E.g., 3/3 runs or 2/20 runs, total trials, confidence/variance if relevant |
| **Control** | Same conditions without the trigger; or changing **one** variable to distinguish hypotheses |
| **Evidence per run** | Directory/logs, timestamps, PID/start time, seed, flags, OS events, checksums |
| **Safety boundary** | Lab/staging only; synthetic data; resource/time caps; never take down production |
| **Known gaps** | Unsimulated external dependencies, redacted data, hard-to-measure concurrency effects |

**Distinguish determinism from probability:** a bug may reproduce 3/3 times on specific input or 2/20 times under 50 concurrent threads. Both are valuable if conditions and denominators are recorded accurately. Never claim “always happens” from one successful run.

### Standardizing a run

1. Initialize the **environment and dataset** matching the chosen commit/artifact hash; document any differences from production.
2. Verify JVM/OS/flags/limits; clean **only authorized lab data**, never deleting original evidence.
3. Start log/timeline collectors in a clean state; record UTC timestamp and run ID.
4. Execute the exact trigger with fixed seed/input/concurrency/timeout where applicable.
5. Measure the oracle independently: exit code/status, logs, health, JFR/GC, and OS events.
6. Stop the experiment safely, gather files and checksums; mark **pass-to-reproduce** or **not-reproduced**.
7. Repeat under identical conditions; run a **negative control**, then change one hypothesis variable at a time.
8. Document remaining discrepancies without hiding failed reproduction attempts.

## 12. Java 17+ Example: Reproducible Java Exception Without a Fatal JVM Crash

This experiment illustrates **how to record triggers and oracles**, without intentionally using JNI, `Unsafe`, or native calls to crash the JVM. An **uncaught Java exception** is an application error and **usually does not produce `hs_err`**.

Save **`IncidentReproDemo.java`**:

```java
public final class IncidentReproDemo {
    private static int parseQuota(String raw) {
        int quota = Integer.parseInt(raw);
        if (quota < 1 || quota > 100) {
            throw new IllegalArgumentException(
                    "quota out of range: " + quota);
        }
        return quota;
    }

    public static void main(String[] args) {
        String scenario = args.length == 0 ? "valid" : args[0];
        String raw = switch (scenario) {
            case "valid" -> "25";
            case "range-error" -> "150";
            case "format-error" -> "many";
            default -> throw new IllegalArgumentException(
                    "unknown scenario: " + scenario);
        };

        System.out.println("scenario=" + scenario);
        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("quota=" + parseQuota(raw));
    }
}
```

Compile and run with JDK 17+:

```bash
javac -g IncidentReproDemo.java
java IncidentReproDemo valid
java IncidentReproDemo range-error
java IncidentReproDemo format-error
```

**Expected behavior logically:**

- `valid` prints `scenario=valid`, `pid=...`, and **`quota=25`**, exiting with a success status when no other environment error occurs.
- `range-error` prints `scenario=range-error`, `pid=...`, then throws `java.lang.IllegalArgumentException` with message **`quota out of range: 150`**. The `quota=...` line is **not printed**, because the exception happens while evaluating the argument before `println`.
- `format-error` prints `scenario=format-error`, `pid=...`, then throws `NumberFormatException` from `Integer.parseInt("many")`.
- PID and stack-trace line numbers depend on JVM/build/source, so **do not fabricate verbatim stdout/stderr**. The scenario can be verified by exception class/message/exit status plus the known initial lines.

To save evidence from a run in a **Linux shell** using a dedicated directory:

```bash
mkdir -p INC-LAB-001/artifacts
javac -g IncidentReproDemo.java

java IncidentReproDemo range-error \
  > INC-LAB-001/artifacts/stdout.log \
  2> INC-LAB-001/artifacts/stderr.log

printf 'exit=%s\n' "$?" > INC-LAB-001/artifacts/exit-code.txt
java -version 2> INC-LAB-001/artifacts/java-version.txt
```

The commands must run in a shell **not configured to abort the whole script on a nonzero Java exit** (such as `set -e`); if `set -e` is enabled, handle the exit status explicitly so evidence saving still runs. `$?` in `printf` captures the exit code of the **immediately preceding `java` command**, with no other command inserted in between.

You can also record a control run:

```bash
java IncidentReproDemo valid \
  > INC-LAB-001/artifacts/control-stdout.log \
  2> INC-LAB-001/artifacts/control-stderr.log
printf 'exit=%s\n' "$?" > INC-LAB-001/artifacts/control-exit.txt
```

Summary: **same JDK, same class, changing one `scenario` variable**. If `range-error` always fails while `valid` always passes, you have demonstrated the contrast **for this example**. Never call it a JVM crash: no fatal error or `hs_err` is expected. In production, linking an example to a real incident requires proving an equivalent input path and logic.

### Reproducers for actual fatal crashes

If the real incident is a `SIGSEGV` in native/JNI code, attempt reproduction **only in an authorized environment** with the exact JDK build, native library, OS/architecture, synthetic dataset, and resource caps. Never ask colleagues to run code that “intentionally crashes the JVM” in production just to fill out a bundle.

A safe recipe for investigators might state: “Feed synthetic input of data class X through JNI parser version Y on staging with the matching native library; wait for callback Z; failure exhibits `SIGSEGV` and problematic frame with the matching signature; if observed, capture `hs_err`/core per prepared policy.” It still requires real measurements and success counts; **never turn a hazardous step into a mandatory requirement**.

## 13. Checksums, Integrity, and Chain of Handover

`hs_err`, `.hprof`, `.jfr`, or core files can change size while still being written; **never hash a file and declare it “complete” before the producer closes it**. Confirm the file is stable, readable, and no longer being written before archiving an immutable copy. For an exported JFR:

```bash
jfr summary /var/log/java/incident.jfr
```

Use the **real filename and exact filesystem**; if `jfr` reports an error, do not mark the JFR as a valid artifact. Once the share-approved evidence files are ready, compute hashes:

```bash
cd INC-LAB-001
sha256sum artifacts/stdout.log \
          artifacts/stderr.log \
          artifacts/exit-code.txt \
          artifacts/java-version.txt \
          > SHA256SUMS.txt
sha256sum -c SHA256SUMS.txt
```

These commands apply to the `INC-LAB-001` bundle when those four files are created as in Section 12. If adding more files, put the **exact existing files** into the hash list. A SHA-256 file only proves **bytes did not change between two checks**, not that the file came from the right origin or was unedited prior to hashing; hence you still need logs of who/when/how it was collected.

Create an archive if permitted:

```bash
cd ..
tar -czf INC-LAB-001.tar.gz INC-LAB-001
sha256sum INC-LAB-001.tar.gz > INC-LAB-001.tar.gz.sha256
```

**Warning:** this archive must contain **only materials approved for sharing and checked for sensitive data**. Never bundle raw heaps, cores, or secrets into a broadly shared archive. Hashing is not encryption. Store sensitive originals in access-restricted storage, while redacted copies carry their own checksums and document what was masked.

### When redaction is needed to protect information

Maintain two distinct tiers:

- **Original, restricted:** unaltered original with hash, capture timestamp, ACLs, and retention deadline.
- **Sanitized, shareable:** copy with tokens, emails, payloads, PII, user details, and command-line/env credentials masked; hash of the copy plus a description of the redaction applied.

You cannot delete a few random lines and call it a sanitized dump. Heaps and cores hold binary data, and text outputs can hide secrets in unobvious places; sometimes **a dump simply cannot be shared** outside an authorized group. For investigation tickets, you may provide **only metadata, signatures, and the restricted vault path**, instead of attaching full data.

## 14. From Evidence to Hypotheses, Without Jumping Straight to Conclusions

Suppose a post-deploy incident shows signs of a fatal error in a JNI library alongside high memory usage. At minimum, distinguish these hypotheses:

| Hypothesis | Potentially supporting evidence | How to falsify |
| --- | --- | --- |
| New native library version introduced a bug | `hs_err` in matching native frame, occurs only on builds with the new library | Run identical input on both native library versions in lab |
| Memory pressure created failure conditions | GC/native memory pressure precedes crash, container near ceiling | Reproduce identical input under a different memory budget, check crash type |
| Input data triggers buggy code path | Crash correlates with specific payload/format, consistent stack path | Equivalent synthetic input vs. control input |
| Concurrency / race | Appears only under high load, many threads/interleavings | Repeat multiple runs, vary concurrency/seed while holding other variables fixed |
| OS kill rather than fatal JVM crash | Kernel/cgroup OOM events, `OOMKilled`, no fatal signature | Check external exit reason, metrics, and kill policy |

A line in `hs_err` may only be **where the fault was detected**. A timing correlation between GC and a crash does not prove GC caused it. State conclusions by tier:

1. **Observed:** “Process exited, kernel reported `OOMKilled`” or “`hs_err` header shows `SIGSEGV`.”
2. **Consistent with:** “Situation is consistent with a race in the native callback.”
3. **Confirmed by controlled reproduction:** “In lab, changing only library version A→B under identical inputs/limits caused the signature to appear only on B across multiple runs.”
4. **Fix validated:** “After the patch, the reproduction test and regression suite no longer exhibit the signature within the stated sample scope.”

Even “0 failures after 100 runs” does not prove zero probability; report exact trial counts and conditions. Avoid writing conclusions broader than the evidence.

## 15. Criteria for a Handover-Ready Bundle

A recipient who did not witness the incident must be able to answer this checklist:

| Check | Passes when |
| --- | --- |
| **Identification** | Clear Incident ID, service, build/commit, JVM version, instance/PID/start time |
| **Classification** | Distinguishes exception, fatal HotSpot crash, OOME, OS kill, or hang |
| **Timeline** | Includes time window with timezone, trigger/crash/restart milestones |
| **Raw facts** | Records evidence filenames/sources/commands; not just screenshots or hearsay |
| **Integrity** | Files are complete; checksums/ownership/retention are managed |
| **Analyzability** | `hs_err`/HPROF/JFR (if present) open/parse cleanly, or missing reason is documented |
| **Reproducer** | Preconditions, trigger, oracle, build/run steps, trial counts, and control results |
| **Safety** | Sensitive data classified, redacted/access-restricted, no secrets leaked |
| **Boundaries** | Hypotheses separated from facts; evidence gaps and uncertainty noted |
| **Handover** | Clear owner, authorized storage location, next actions, and remediation metrics |

If a criterion fails, explicitly state **insufficient** rather than fabricating artifacts or shortcutting to an unfounded conclusion. A bundle lacking a core due to policy restrictions can still be **sufficient to guide next steps** if it includes the signature and a follow-up collection/repro plan; a minimal bundle does not mean blindly checking off every possible file regardless of context.

### Signs a bundle is insufficient

- “Failed a few days ago” with no time, timezone, or process instance.
- Saving only a truncated stack trace missing the exception message, `Caused by`, or thread context.
- Having a huge heap dump without knowing JDK build, `-Xmx`, or pre-OOME trends.
- Having `hs_err` without native libraries/builds/symbols, or not knowing if the file is intact.
- Providing only the command “`java -jar app.jar`” when the JAR has no version/hash and the input was lost.
- Reproducing 1/1 time and claiming “always happens,” ignoring 10 earlier failed reproductions.
- Monitoring screenshots lacking timestamps/timezones, axis units, or filter scope.
- Dumping raw env vars containing secrets into a public ticket “to be thorough.”
- `.jfr` files not checked with `jfr summary`, or containing only the period **after** the incident.
- Copying `hs_err` to a shared folder without checking permissions or retention.

## 16. Common Mistakes and How to Fix Them

1. **Assuming every Java exception is a JVM crash.** Java stack traces usually do not create `hs_err`; classify first.
2. **Trying to run `jcmd` after the process is dead.** You cannot query a nonexistent JVM; focus on files and OS evidence.
3. **Letting restarts overwrite or delete logs.** Snapshot/copy before cleanup when possible, and log restart timestamps.
4. **Confusing PID with immutable identity.** PIDs get reused; record process start time and instance ID.
5. **Assuming missing `hs_err` proves no fatal error.** Paths, permissions, disk, or kills can prevent file creation.
6. **Assuming `SIGKILL/137` proves OOM.** Many causes lead to kills; check OS/orchestrator evidence.
7. **Assuming a heap dump explains native memory.** HPROF shows only part of the picture.
8. **Collecting cores/heap dumps unconditionally.** Carries pause, disk, and security risks; require an investigative question and approval.
9. **Omitting JDK vendor/update/native library versions.** Insufficient for binary-dependent crash analysis.
10. **Putting secrets into the manifest.** Never store raw env/command lines without security review.
11. **Saying “reproducible” without recording the trigger.** Colleagues cannot verify it.
12. **Skipping a control case.** Hard to tell which input, flag, or traffic pattern caused the failure.
13. **Fabricating stdout/exit status or “3/3” reproductions.** If unexecuted, mark as expected and note the gap.
14. **Mixing metrics across timezones.** Timelines can create false causality.
15. **Hashing after editing original files.** No longer verifies the exact incident-time bytes.
16. **Hashing files still being written.** The hash will not match the final artifact.
17. **Using checksums as a security mechanism.** Hashing neither encrypts nor restricts access.
18. **Sending sensitive binary files over open channels.** Cores and heaps can contain tokens and customer data.
19. **Assigning root cause straight from the problematic frame.** Where the fault surfaces differs from where corruption started.
20. **Declaring “fixed” after a single clean run.** Repeat across equivalent frequencies and conditions.

## 17. Practice Exercises and Self-Assessment

**Exercise 1 — what kind of incident?** The app prints `Exception in thread "main" java.lang.IllegalArgumentException` and exits nonzero; no `hs_err`. What should the minimal bundle contain?

*Hint:* Source/build, command/input, Java stderr/stack, exit status, JVM version, expected/actual, and reproducer. Core dump and fatal error log are not required.

**Exercise 2 — fatal native JVM crash:** You have `hs_err_pid12345.log` with problematic frame in `libparser.so`, yet no core due to OS policy. Can you conclude that library is definitely the root cause?

*Hint:* Not yet. Preserve the fatal log, JDK/native builds, flags, library version, OS, timeline, and note the missing core. Build a lab reproducer to test the hypothesis without calling the frame a confirmed root cause.

**Exercise 3 — OOMKilled:** A container exits 137 with no heap dump. Can you conclude a Java heap leak?

*Hint:* No. Read kernel/cgroup/orchestrator events and container limits; 137 could be `SIGKILL` from another source. Absence of a heap dump rules out neither an OOM kill nor native memory pressure.

**Exercise 4 — time:** JFR reports a GC pause at 09:20 UTC, and app logs show a request at 16:20 GMT+7. Do those two timestamps match in real time?

*Hint:* 09:20 UTC equals 16:20 in Vietnam on the same date. Still verify exact date, seconds, and clock skew before inferring causality.

**Exercise 5 — reproduction:** Run A fails 2/20 times at 100 requests/s; run B has 0/5 failures at 10 requests/s. Does that prove load is the cause?

*Hint:* Not yet; both workload and sample size differ. Design more trials with identical build/input/limits, varying one variable per round and recording both negative and positive outcomes.

**Exercise 6 — sharing:** A heap dump contains session tokens and customer payloads. Should it be attached directly to a public issue tracker?

*Hint:* No. Store only in an authorized location with ACLs, encryption, and retention; a public ticket only needs the signature, manifest, and restricted-access reference. Redacted copies get their own hashes.

**Exercise 7 — run the example:** Compile `IncidentReproDemo.java`, create `INC-LAB-001` using the commands in Section 12, compare `stdout.log`/`stderr.log`/exit-code of `range-error` against `valid`, and compute SHA-256. Write a five-line `README` describing classification, expected/actual, oracle, missing evidence, and the next verification step.

## 18. Official References

- [Oracle JDK 21 — Prepare Java for Troubleshooting: enabling flags beforehand and gathering relevant data](https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html).
- [Oracle JDK 21 — Fatal Error Log: locations, header, threads, process, and system sections](https://docs.oracle.com/en/java/javase/21/troubleshoot/fatal-error-log.html).
- [Oracle JDK 21 — `java` launcher: `-XX:ErrorFile`, `-XX:+HeapDumpOnOutOfMemoryError`, and `-XX:HeapDumpPath`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle JDK 21 — `jcmd`: `Thread.print`, `VM.version`, `VM.flags`, `JFR.dump`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — `jfr`: `summary`, `print`, and inspecting files](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [Oracle JDK 21 — Troubleshoot Memory Leaks: distinguishing `Java heap space` and other OOME forms](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html).

**Practical takeaway:** A solid evidence bundle lets others **verify for themselves**, rather than forcing them to take a story on faith. Hand over **symptoms + context + timeline + verifiable raw artifacts + reproduction recipe + uncertainty bounds**. State a root cause only when evidence and experiments are strong enough; never sacrifice data confidentiality or production stability just to add one more file.

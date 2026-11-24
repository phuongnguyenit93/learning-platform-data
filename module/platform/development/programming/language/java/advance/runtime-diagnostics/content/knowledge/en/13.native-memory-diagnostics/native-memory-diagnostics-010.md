# 13.10 NMT Overhead, Evidence to Preserve, and the Limit on Re-Enabling After Shutdown

> **Context:** Java 21 / HotSpot, topic **native memory**. Native Memory Tracking (NMT) is a HotSpot tool for tracking a portion of memory managed by the JVM itself. This lesson focuses on **the cost of enabling NMT**, **evidence to capture and preserve before turning it off**, and **the inability to re-enable it in the same process after `shutdown`**. This is an operational decision that must be planned at JVM startup, especially when diagnosing production systems.

## 1. Learning Outcomes

After completing this lesson, you should be able to explain and perform:

1. Distinguish the three startup configuration states `off`, `summary`, and `detail`; understand what NMT collects, what it misses, and its operational costs.
2. Read `reserved`/`committed` and use `baseline`, `summary.diff`, and `detail.diff` matching the enabled level; avoid mistaking an instantaneous delta for proof of a memory leak.
3. Capture complete snapshots, baselines/diffs, JVM version/configuration, timestamps, and OS metrics **before** running `VM.native_memory shutdown`.
4. Explain why `jcmd` **cannot enable or re-enable NMT** once it is `off`/`shutdown`, and how to organize a controlled restart when further diagnostics are needed.
5. Evaluate NMT overhead with representative testing and design an access-controlled evidence-preservation runbook.

## 2. What Does NMT Track and Where Are Its Limits?

NMT (Native Memory Tracking) belongs to the **HotSpot JVM**. It records many memory allocations and mapped regions managed internally by the JVM, presenting them in categories such as `Java Heap`, `Class`, `Thread`, `Code`, `GC`, `Compiler`, `Internal`, `Symbol`, `Native Memory Tracking`, etc. Category names may vary by version/build and configuration. NMT also tracks the memory used **for tracking itself**.

However, NMT is **not** an analyzer for all RAM of a process:

- NMT tracks memory inside **HotSpot** and does not cover every allocation from **third-party native libraries, JNI**, JDK class libraries, or native applications as bounded in the JDK 21 documentation.
- NMT does not list live Java objects on the heap by retained size. The `Java Heap` line shows the JVM-managed memory region and does not replace a heap dump when finding objects holding references.
- NMT does not guarantee an explanation for gaps between JVM figures and OS-reported **RSS** or container memory usage. RSS, page cache, mapped regions, and allocations outside NMT's scope require dedicated OS/container tools.
- Even when NMT has data, certain very early allocations or chunked mechanisms like arenas may not be broken down into individual allocations. Nor is `detail` a recorder of **every** `malloc` call or application stack trace.

**`reserved` and `committed` are not synonymous:** `reserved` is virtual address space set aside by the JVM, while `committed` is the portion committed for use within that virtual space. `committed` **does not automatically equal resident RSS**; do not sum `reserved` across categories and call it physical memory consumed.

Example of reading hypothetical figures:

```text
Total: reserved=4096MB, committed=950MB
- Java Heap (reserved=3072MB, committed=700MB)
- Thread    (reserved=256MB,  committed=18MB)
```

The lines above **illustrate meaning only**, not fixed stdout of a specific JDK or command. They do not prove the process is using exactly 950 MB of RSS or 256 MB of physical stack memory.

## 3. Choosing an NMT Level and Measuring Cost

### 3.1. Level Can Only Be Chosen at Startup

```bash
java -XX:NativeMemoryTracking=off -jar app.jar
java -XX:NativeMemoryTracking=summary -jar app.jar
java -XX:NativeMemoryTracking=detail -jar app.jar
```

These are **three mutually exclusive startup options**, not run together simultaneously. Replace `app.jar` with your real application and verify the target process's Java runtime/flags.

| Level | Available Data | Trade-Off |
| --- | --- | --- |
| `off` (default) | No NMT snapshots/baselines/diffs | No tracking overhead; cannot invoke `jcmd` to enable NMT later |
| `summary` | `reserved`/`committed` totals by subsystem, splitting NMT-reported allocation types | Sufficient to locate growing memory categories; still adds CPU and tracking metadata |
| `detail` | `summary` data plus address regions and aggregation by HotSpot allocation call site | Aids deeper isolation, but requires planning ahead; larger reports, so collection/writing and tracking can consume more resources |

Do not assume `jcmd <PID> VM.native_memory detail` **upgrades** a process already running `summary`. The level is set **at JVM startup**; to get `detail` call-site data, start a new JVM with `-XX:NativeMemoryTracking=detail`.

### 3.2. CPU, Memory, and Diagnostic Operation Cost

Per **Oracle JDK 21** documentation, enabling NMT can incur roughly **5–10% performance overhead** under documented conditions. This is a **reference estimate**, not a fixed add-on factor for every service. Java 21 also notes metadata overhead of roughly **two machine words per NMT-tracked `malloc` allocation**; actual cost depends on allocation frequency and type, thread count, JVM build, hardware, and workload. NMT reports part of its own overhead.

Distinguish three cost components:

1. **Continuous tracking:** updating statistics whenever HotSpot allocates/frees native regions; adds metadata and can reduce throughput.
2. **Querying via `jcmd`:** `VM.native_memory` is classified **Impact: Medium** in JDK 21; `detail` output in particular can be long, consuming processing time and I/O.
3. **Storing/rotating evidence:** output files, parsers, extraction from containers, and retaining multiple snapshots also consume storage, bandwidth, and operational effort.

Do not treat `5–10%` as a maximum, minimum, or exact forecast. Always **measure directly** on a representative workload. Workloads with heavy native allocations or strict latency budgets may behave differently.

### 3.3. How to Measure Overhead Meaningfully

In staging or an approved canary, compare three deployments with identical JDK 21 build, heap/GC flags, host or container limits, input data, request rate, concurrency, and warm-up:

- **No-NMT baseline:** `-XX:NativeMemoryTracking=off`.
- **Tracking group:** `-XX:NativeMemoryTracking=summary`.
- **Deep analysis group:** `-XX:NativeMemoryTracking=detail` if call sites are genuinely required.

Record **throughput**, p50/p95/p99 latency, CPU usage, GC frequency/pauses, RSS and container memory limit, thread count, errors, and NMT committed where available. Repeat measurements to avoid deciding from a single run, documenting conditions and variance. Use realistic load scale; a few-second startup test cannot predict sustained overhead.

You can calculate percentage change in throughput for a measurement run:

```text
Throughput change (%) =
    (throughput_with_NMT - throughput_without_NMT)
    / throughput_without_NMT × 100
```

For example, dropping from 1,000 requests/s to 940 requests/s is **-6% throughput** under those test conditions. This **does not mean** CPU always increases by exactly 6% or every system slows by 6%. For latency, report both **millisecond delta and percentage** at the same percentile.

If you only need native memory diagnostic readiness in production, `summary` may be a reasonable baseline after load testing; if continuous call sites are needed, `detail` must be proven acceptable. Never enable `detail` out of habit across every replica.

## 4. Collecting Evidence While NMT Is Enabled

### 4.1. Verifying the Right JVM

`jcmd` must run on the same host as the JVM with appropriate effective UID/GID; container PID namespaces can prevent `jcmd -l` on the host from seeing the target JVM. Verify the target JVM via service manager, pod/host, and PID before collecting data. Avoid `jcmd 0` because PID `0` can broadcast commands to multiple JVMs.

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.uptime
jcmd <PID> VM.command_line
jcmd <PID> help VM.native_memory
```

`<PID>` is a placeholder to replace with the real PID. **`VM.command_line` may contain configuration secrets** if tokens/passwords are passed in arguments; store and share outputs under access-control policies, redacting sensitive parts in broadly shared copies.

Normally no mutating command is needed to check NMT: when NMT is enabled, query:

```bash
jcmd <PID> VM.native_memory summary scale=KB
```

If NMT is inactive, the command will not yield useful tracking data. Do not confuse inability to attach due to permissions/namespaces with NMT being disabled: they are two independent causes.

### 4.2. Snapshot, Baseline, and Diff

A **baseline** is a comparison checkpoint held **inside the running process**, not a permanently persisted evidence file. Set the baseline after warm-up and once load is in a comparable state; setting it immediately at startup captures normal growth from class loading, JIT, and thread pools in the deltas.

```bash
# JVM started with -XX:NativeMemoryTracking=summary or detail
jcmd <PID> VM.native_memory summary scale=KB
jcmd <PID> VM.native_memory baseline
# Let realistic workload run over a meaningful interval
jcmd <PID> VM.native_memory summary.diff scale=KB
jcmd <PID> VM.native_memory summary scale=KB
```

On a JVM **started with `detail`**, you can also collect:

```bash
jcmd <PID> VM.native_memory detail scale=KB
jcmd <PID> VM.native_memory detail.diff scale=KB
```

- `summary`: absolute state of categories at query time.
- `baseline`: sets the comparison checkpoint inside the JVM. A new baseline changes the reference used by subsequent `*.diff` calls; **export the old record to a file before resetting the checkpoint**.
- `summary.diff`: delta by subsystem relative to the most recent baseline; negative signs indicate decrease, positive signs indicate increase.
- `detail` and `detail.diff`: include corresponding call-site data only when started in `detail`. You cannot reconstruct call-site history if you previously ran `summary`.

A positive delta does not equal a leak: rising class counts, JIT warm-up, thread stack reservations, metaspace growth, or memory caching can all be legitimate. Compare by load and time. NMT provides snapshots of **cumulative state**, without pointing directly to a "culprit" Java object or method.

### 4.3. What to Preserve — Even Before Considering `shutdown`

| Evidence Group | What to Save | Why |
| --- | --- | --- |
| **JVM Identity** | Service, hostname/pod, process PID **and start time**, JDK 21 vendor/build, container image, GC, `-Xmx`, NMT config | PIDs can be reused; restarts begin a separate observation series |
| **Measurement Context** | Timestamp with timezone, uptime, workload, concurrency/QPS, app version, warm-up or deploy timing | Distinguishes normal operational changes from abnormal growth |
| **Start-of-Window NMT** | `summary` output at baseline time, confirmation baseline was set; if `detail` is on, initial `detail` report | Preserves absolute state independent of the live JVM baseline |
| **End-of-Window & Intermediate NMT** | `summary`, `summary.diff`; if at `detail`, also `detail`, `detail.diff` | Captures both absolute values and deltas to investigate growing categories and call sites |
| **OS / Container Metrics** | RSS, environment-specific memory.current/working set, limits, swap, thread count, maps/smaps if permitted, OOM errors | Reconciles regions outside NMT's scope and real impact |
| **Integrity & Access Control** | Filename, checksum, storage location, owner, ACLs, retention, record of authorized viewers | Native diagnostics can reveal library names, paths, and memory addresses |

**Preserve raw outputs** with recorded units (`scale=KB` is easy to compare), attaching timestamps to metadata; you may build tables/charts from copies, but **never keep only a screenshot** or a single total figure. A `summary.diff` alone cannot reconstruct before/after states; if the JVM dies or NMT is shut down, the internal baseline can no longer be queried.

### 4.4. Example Saving Data to a Restricted-Access Directory

The Linux shell example below illustrates a diagnostic session; the operator must **fill in the exact PID** and run only with permission to attach/save files:

```bash
umask 077
mkdir -p "$HOME/nmt-evidence"
chmod 700 "$HOME/nmt-evidence"

# Fill in the exact PID of the target JVM, e.g.:
TARGET_PID=12345
EVIDENCE_DIR="$HOME/nmt-evidence"

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$EVIDENCE_DIR/00-time-before.txt"
jcmd "$TARGET_PID" VM.version > "$EVIDENCE_DIR/01-vm-version.txt"
jcmd "$TARGET_PID" VM.uptime > "$EVIDENCE_DIR/02-uptime-before.txt"
jcmd "$TARGET_PID" VM.native_memory summary scale=KB > "$EVIDENCE_DIR/03-summary-before.txt"
jcmd "$TARGET_PID" VM.native_memory baseline > "$EVIDENCE_DIR/04-baseline.txt"
```

After a representative load observation interval:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$EVIDENCE_DIR/05-time-after.txt"
jcmd "$TARGET_PID" VM.native_memory summary.diff scale=KB > "$EVIDENCE_DIR/06-summary-diff.txt"
jcmd "$TARGET_PID" VM.native_memory summary scale=KB > "$EVIDENCE_DIR/07-summary-after.txt"
jcmd "$TARGET_PID" VM.uptime > "$EVIDENCE_DIR/08-uptime-after.txt"
```

If `detail` was enabled, run and save `detail` and `detail.diff` **before shutdown**. Check every exit code and file content: shell redirection still creates an empty file when `jcmd` fails. The example above does not automatically collect RSS; OS/container metrics must be captured and named at the same timestamps using the appropriate OS tools.

Do not use the sample path `$HOME/nmt-evidence` when your environment mandates a specific directory policy; production evidence directories should follow **encryption, audit, rotation, and retention** policies. Do not post output containing internal paths/addresses to public tickets or repositories.

## 5. `shutdown`: A One-Way Step Within the Same JVM

This is the most critical operational constraint of this lesson.

### 5.1. Supported State Transitions

```text
Start JVM with -XX:NativeMemoryTracking=off
    -> NMT off -> cannot enable NMT via jcmd

Start JVM with -XX:NativeMemoryTracking=summary
    -> NMT summary -> can query summary/baseline/diff
                   -> jcmd ... VM.native_memory shutdown -> NMT off
                   -> cannot re-enable in the same JVM

Start JVM with -XX:NativeMemoryTracking=detail
    -> NMT detail -> can query detail and summary/baseline/diff
                  -> jcmd ... VM.native_memory shutdown -> NMT off
                  -> cannot re-enable in the same JVM
```

Per **Oracle JDK 21**, `jcmd` **can stop NMT, but cannot start or restart NMT**. There is no standard procedure calling `VM.native_memory enable`, nor can you use `VM.set_flag` to turn a JVM started with `off` into `summary`/`detail`.

To intentionally stop NMT on a JVM that currently has it enabled:

```bash
# ONLY do this after saving all data you need to keep:
jcmd <PID> VM.native_memory shutdown
```

This is a **runtime-state-mutating command**, unlike read-only `summary`. Do not run it in production as an accidental test. After `shutdown`:

- No further `summary`/`detail` snapshots or NMT diffs can be collected from that process.
- The live JVM baseline and tracking data cannot be queried retroactively to recover unexported history.
- NMT will not record allocations occurring after shutdown, so previously captured evidence describes only the past window.
- If continued tracking is needed, you must **start a new JVM** with `-XX:NativeMemoryTracking=summary` or `detail`, set a **new baseline**, and label it a new measurement series rather than chaining it as one continuous session.

Shutting down NMT **does not shut down the Java application**. Do not confuse `VM.native_memory shutdown` with terminating the process via `jcmd`. Still, restoring NMT requires restarting the JVM, incurring availability impact and potential state loss; plan rollout accordingly.

### 5.2. Should You Shut Down to Reduce Overhead?

Once enough evidence is collected, operators may wish to shut down tracking to eliminate ongoing overhead. Before deciding:

1. Confirm the investigation phase **is finished** and all required snapshots and raw diffs are saved and retrievable.
2. Confirm you accept **having no NMT** on this JVM going forward; if the issue recurs before the next restart, you will have to rely on other telemetry.
3. Define which thresholds trigger a **rolling restart** to re-enable NMT, who is authorized to perform it, and whether restarting drops evidence/state.
4. If the goal is long-term overhead savings, validate via measurement rather than assuming `shutdown` automatically restores exactly 5–10% throughput. Already-allocated metadata, JVM state, and workload still have an effect.
5. Do not delete evidence files in the same shutdown step; retain them under agreed retention and access policies.

For multi-replica apps, consider keeping `summary` on a canary whose overhead is measured, or using scheduled diagnostic windows. For services requiring continuous uptime, plan OS-tool investigations when NMT is absent.

### 5.3. When NMT Was Already Off or Too Coarse

**Scenario A — JVM started `off`:** `jcmd` cannot fabricate past NMT data. To obtain NMT, add the startup flag to deployment config and perform a controlled JVM **restart**. In the meantime, use RSS, cgroup memory, thread counts, and `/proc/<PID>/smaps_rollup`/`pmap` where applicable and permitted; these tools do not replace HotSpot NMT breakdowns.

**Scenario B — JVM started `summary`, now call sites are needed:** You cannot upgrade to `detail` via a `jcmd` command on the same JVM. Export all `summary`/diffs first, then deploy a new JVM with `detail`, take a new baseline, and collect call sites over a representative window.

**Scenario C — `shutdown` was just run:** If outputs were not saved, missed NMT snapshots cannot be recovered from the same JVM. You can retain external OS metrics/logs; to resume NMT tracking, restart with the flag configured from startup.

**Scenario D — JVM crash:** Distinguish crashes, `OutOfMemoryError`, container kills, and graceful exits. `-XX:+UnlockDiagnosticVMOptions -XX:+PrintNMTStatistics` can print NMT stats when the JVM **exits along supported paths** if tracking was enabled at startup; it does not guarantee a report on abrupt kills, nor can it recover tracking that was shut down.

## 6. Safe Hands-On Practice on Java 21

Lab objective: observe the difference between **absolute snapshots**, **baseline checkpoints**, **diffs**, and **the shutdown boundary** using controlled platform-thread creation. Do not use production data or try to create a real memory leak.

Create **`NmtLab.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class NmtLab {
    public static void main(String[] args) throws Exception {
        BufferedReader input = new BufferedReader(new InputStreamReader(System.in));
        System.out.println("BASELINE READY");
        System.out.println("Press ENTER to start 12 platform threads");
        input.readLine();

        CountDownLatch ready = new CountDownLatch(12);
        CountDownLatch release = new CountDownLatch(1);
        List<Thread> workers = new ArrayList<>();

        for (int i = 0; i < 12; i++) {
            Thread worker = new Thread(() -> {
                ready.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "nmt-worker-" + i);
            workers.add(worker);
            worker.start();
        }

        ready.await();
        System.out.println("WORKERS READY: " + workers.size());
        System.out.println("Press ENTER to release workers");
        input.readLine();

        release.countDown();
        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("DONE");
    }
}
```

In **terminal A** with JDK 21, run interactively:

```bash
javac NmtLab.java
java -XX:NativeMemoryTracking=summary -Xms32m -Xmx128m NmtLab
```

When `BASELINE READY` appears, **do not press ENTER yet**. Switch to **terminal B** on the same host as the appropriate user:

```bash
jcmd -l
jcmd <LAB_PID> VM.native_memory summary scale=KB
jcmd <LAB_PID> VM.native_memory baseline
```

Replace `<LAB_PID>` with the exact PID of `NmtLab`. Return to terminal A and press ENTER **once**. When `WORKERS READY: 12` appears, do not press ENTER a second time; switch back to terminal B:

```bash
jcmd <LAB_PID> VM.native_memory summary.diff scale=KB
jcmd <LAB_PID> VM.native_memory summary scale=KB
```

Watch `Thread` and related categories. Creating 12 **platform threads** typically increases reserved thread-stack memory, though **exact deltas and committed values** depend on the OS/JVM and stack allocation behavior; do not expect one fixed number or treat a zero diff as proof of broken code.

After **saving outputs** in your lab environment, you can try:

```bash
jcmd <LAB_PID> VM.native_memory shutdown
jcmd <LAB_PID> VM.native_memory summary
```

The second command no longer returns active NMT tracking data. Do not expect one fixed error string because wording can vary by build. Finally, return to terminal A and press ENTER a second time to release and `join()` the workers.

**Application stdout** on terminal A (ignoring shell prompts and `jcmd` output) is:

```text
BASELINE READY
Press ENTER to start 12 platform threads
WORKERS READY: 12
Press ENTER to release workers
DONE
```

`Thread`, `CountDownLatch`, and `BufferedReader` use standard Java APIs, requiring no preview features. The lab creates platform threads rather than virtual threads to make native stack memory easier to observe; NMT's `Thread` count may include JVM internal threads and does not equal just the 12 workers created.

### 6.1. Comparing `summary` with `detail`

Start a **fresh lab run** (a new JVM), changing the startup flag to:

```bash
java -XX:NativeMemoryTracking=detail -Xms32m -Xmx128m NmtLab
```

At the same two checkpoints as above, you can save `detail` and `detail.diff`:

```bash
jcmd <LAB_PID> VM.native_memory detail scale=KB
jcmd <LAB_PID> VM.native_memory baseline
# After starting 12 platform threads
jcmd <LAB_PID> VM.native_memory detail.diff scale=KB
```

The `detail` run must be a **new JVM** with a new PID and new baseline. Do not compare call-site numbers from the `detail` run with `summary` numbers from the old JVM as if they formed a single continuous series. A growing category shows **where HotSpot recorded growth**, not confirmation of a leak without trends and reproducibility.

## 7. How to Interpret When NMT and OS Memory Disagree

| Observation | Possibilities to Check | Conclusion Not to Jump To |
| --- | --- | --- |
| NMT `committed` grows, RSS nearly flat | Reserved/committed differ from resident, untouched pages, JVM activity shift | "The JVM is definitely leaking native memory" |
| RSS climbs sharply, NMT `committed` fails to match | Native allocations outside HotSpot, library mmaps, cgroup/page cache, memory accounting | "NMT is broken" or "definitely no leak" |
| NMT `Thread` grows | Platform thread count, stack reserve/commit, thread lifecycle | "All threads leaked" from a single snapshot |
| `Class`/`Code` grows after startup | Class loading, metaspace, JIT compilation, and caches | "Leak" before warm-up stabilizes |
| `summary.diff` drops after GC or load drop | Uncommitted/freed regions, workload change, earlier baseline timing | "Leak fixed" if long-term time series still climbs |
| `detail.diff` points to a HotSpot call site | JVM allocation site involved in growth | "Found the leaking Java business method" without tracing code paths |
| No data after `shutdown` | Tracking stopped; jcmd cannot restart it | "Can re-enable right away with `VM.set_flag`" |

Clarify **trend** analysis: collect at least two checkpoints with comparable workload/conditions, marking deploys, traffic, GC, class loading, and baseline reset timestamps. If new data contradicts the leak hypothesis, update the hypothesis. For growth outside NMT's scope, use OS native memory profiling, allocator telemetry, or platform-appropriate tools in authorized environments.

## 8. Production Decision Runbook

### Before Enabling NMT

- [ ] Define the question: do you need subsystem totals (`summary`) or call sites (`detail`)?
- [ ] Identify **JDK vendor/build**, JVM image, and exact startup command. NMT must be enabled **before the JVM starts**.
- [ ] Measure cost under representative workload: CPU, throughput, p95/p99, RSS, limits, and errors.
- [ ] Define observation duration, snapshot cadence, storage location, quotas, owners, viewer permissions, and retention.
- [ ] Schedule a deploy/rolling-restart window if changing tracking levels; communicate expected impact and rollback plans.

### During Investigation

- [ ] Verify PID + start time, NMT level, and `jcmd` permissions; never broadcast commands to multiple JVMs.
- [ ] Capture a post-warm-up snapshot **before** setting the baseline; record UTC timestamps/uptime.
- [ ] Collect `summary.diff`/`summary` under matching workloads; if `detail`, also collect raw call-site reports.
- [ ] Record RSS, cgroup/OS memory, thread counts, and deploy/GC events on the same timeline.
- [ ] Protect saved data; verify exit codes, non-empty files, and checksums when moving to long-term storage.

### Before `VM.native_memory shutdown`

- [ ] Saved complete raw snapshots, baseline timestamp, diffs, and version/flags/JVM identity.
- [ ] Recorded the time tracking ended and who authorized shutting it down.
- [ ] Accepted losing the ability to continue NMT on the current JVM.
- [ ] Have a plan to re-enable **by restarting a new JVM**, without relying on `jcmd` to turn it back on.
- [ ] If doubts remain or an incident is active, defer shutdown and seek approval from the operations lead.

### After Shutdown

- [ ] Continue monitoring OS/container metrics; mark the period without NMT coverage.
- [ ] If further investigation is needed, deploy a JVM with the NMT startup flag, set a baseline, and start a new data series.
- [ ] Ensure snapshots/PIDs from different restarts are not mixed when comparing.
- [ ] Delete/rotate files per TTL while preserving evidence per incident policy.

## 9. Mistakes to Avoid

**"Once NMT is off, it can be re-enabled with `jcmd`."** False per Java 21. `jcmd` can `shutdown`, not `start`/`restart` NMT. A new JVM restart with the flag is required.

**"`summary` can be upgraded to `detail` at runtime."** No. Call-site tracking must be chosen at startup; there is no way to retroactively recover past allocations from summary data.

**"After `shutdown`, you can still query old NMT numbers."** Do not rely on this. In-JVM snapshots/baselines do not substitute for exported files. **Export data before shutting down.**

**"Enabling NMT always costs only 5% CPU."** Inaccurate. Documentation notes **5–10% performance overhead**, and only testing with real workloads reveals the impact on your specific service and percentiles.

**"`reserved` equals RAM used."** False. Do not compare total reserved directly against RSS or container memory limits.

**"NMT covers all native code."** False. JNI, third-party libraries, and many allocations outside HotSpot are not covered by NMT. When NMT cannot explain RSS, cross-check OS tools/native profilers.

**"Saving only `summary.diff` is enough."** Lacks context. Always save absolute snapshots, baseline timestamp, JVM configuration, and environment metrics before shutting down.

## 10. Reference Documentation (Java 21)

1. [Oracle JDK 21 — Native Memory Tracking: levels, overhead, shutdown, and restart limits](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html)
2. [Oracle JDK 21 — Diagnostic Tools: reading reserved/committed, NMT overhead, baseline/diff, and tracking scope](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
3. [Oracle JDK 21 — `jcmd` specification: `VM.native_memory` and command impact](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
4. [Oracle JDK 21 — Troubleshoot Memory Leaks: NMT scope and native code outside the JVM](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html)

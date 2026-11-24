# 12.6 Planning Pause Duration, Disk Space, and Dump File Permissions

> **Context:** Java 21, diagnosing Java heap leaks or growth using HPROF **heap dumps**. This lesson aims to build a safe operational plan before capturing a dump on a running application: service impact, storage capacity, file creation/read permissions, security, and recovery procedures. Shell examples target Linux; the same principles apply to Windows and containers using appropriate paths, permissions, and tools.

## 1. Why Plan Before Triggering a Heap Dump?

A heap dump is a snapshot of Java objects on the heap along with the class metadata and references needed for analysis. It helps trace retained objects, but it is **not** a copy of total process RAM: native memory, file descriptors, socket buffers, and many off-heap resources are not fully represented. You cannot deduce total RSS or the entire cause of an `OutOfMemoryError` from an HPROF file alone.

Collection typically runs into three operational constraints:

1. **Pause duration / latency:** the JDK 21 `jcmd` documentation marks the heap dump command as **Impact: High**, depending on heap size and contents. By default, the command requests a **full GC** before dumping; inspection and writing can freeze or severely slow the application, causing timeouts, failed health checks, and dropped throughput. There is no fixed pause guarantee.
2. **Disk space and I/O:** dumps can be huge, requiring enough space on the **filesystem as seen by the target JVM** plus write bandwidth; filling a disk impacts the application, logs, databases, or the node itself.
3. **Permissions and security:** dumps can contain strings, request objects, sessions, tokens, customer data, and internal state still sitting in the heap. The account running the JVM needs write permission, while others should be granted read access only on a strict need-to-know basis.

Therefore, requesting a dump is an **operationally risky diagnostic action**. Decide approvers, execution window, storage target, verification steps, transfer destination, retention TTL, and abort/recovery plans before running the command.

## 2. Choosing the Right Capture Method for the Situation

| Capture method on Java 21 | Timing | Impact / notes | When to use |
| --- | --- | --- | --- |
| `jcmd <PID> GC.heap_dump <file>` | Proactive on a live JVM | **Impact: High**; requests full GC by default; writes HPROF to target JVM's filesystem | Need a controlled snapshot before restarting or when leak symptoms appear |
| `jcmd <PID> GC.heap_dump -all <file>` | Proactive | Includes unreachable objects, does not request full GC **from this command**; still a high-cost dump | Need to see unreachable objects as well and understand the semantic difference |
| `jcmd <PID> GC.heap_dump -gz=1 <file.gz>` | Proactive | Gzip compression level 1 (fastest among levels 1–9), trading CPU/time for smaller size; no guaranteed compression ratio | When disk space is tight, after testing on a similar workload |
| `-XX:+HeapDumpOnOutOfMemoryError` with `-XX:HeapDumpPath` | Automatic when JVM raises a supported OOME | Must be configured **before startup**; failure conditions may prevent writing (disk full, JVM killed, bad permissions) | Want evidence when failures reproduce unpredictably and cannot be timed manually |

**Do not confuse `-all` with a "zero-downtime" mode.** This option changes the object set and drops the default full GC request, yet the dump operation can still block the JVM and take a long time. Nor is `-gz=1` guaranteed to reduce total wall-clock time, since compression consumes CPU.

If the goal is merely to observe heap growth trends, consider starting with **GC logs, heap metrics over time, JFR, or telemetry**. `GC.class_histogram` can assist investigations, though `jcmd` also classifies it as **Impact: High**. Escalate to a heap dump only when the evidentiary value justifies the operational cost.

## 3. Budgeting Time and Service Impact

### 3.1. Separating three durations

- **Dump command execution time:** from issuing the command until `jcmd` returns; includes coordinating with the JVM, GC if requested, taking the snapshot, and writing the file.
- **Application unresponsiveness / slowdown duration:** measured via real metrics (request latency, error rate, health checks, throughput). Do not automatically equate this with total command wall-clock time or GC time alone.
- **Post-dump handling time:** checking size, computing checksums, moving, encrypting, and analyzing; can continue creating I/O pressure if stored on the same disk as the application.

Make a rough engineering estimate using **expected dump size / measured sustained write throughput**, plus JVM/GC overhead and contention. Use this as a starting point to size the **maintenance window**, not as an upper bound or SLA.

**Planning math example only:** If an HPROF is expected around 8 GiB and the storage sustains about 150 MiB/s, the raw data write alone gives `8192 MiB / 150 MiB/s ≈ 55 seconds`. Full GC, serialization formatting, I/O contention, and throttling can make total duration much longer. Never conclude "the pause will be exactly 55 seconds."

### 3.2. Pre-execution plan

Before dumping a production service, align on the following:

- **Evidence goal:** snapshot during heap growth, before restart, or automatic on OOME? One snapshot or multiple, and when is data representative?
- **Acceptable impact thresholds:** SLO/p95/p99, request timeouts, readiness/liveness probes, error budget, remaining serving replicas, and ability to drain traffic.
- **Time window:** prefer low-traffic hours; operate one instance at a time across replicas, preserving reserve capacity. Have someone watching metrics who knows when to abort.
- **Impact mitigation:** drain traffic away from the target instance if architecture allows; investigate on an isolated replica with representative state/load; test first in staging with the same collector, JDK, and storage class.
- **Contingency plan:** if the dump stalls, error rates spike, or the volume nears capacity, have rollback, traffic switching, or restart procedures ready. Canceling the diagnostic client command does not necessarily abort ongoing work inside the JVM immediately.
- **Decision authority:** identify who is authorized to trade availability for evidence, who monitors system health, and who is cleared to handle sensitive files.

**Important:** Testing with a small heap does not accurately predict dump duration for a large heap; Java build, GC, object count, live ratio, disk speed, load, and storage type all matter. Staging timings are a reference, not a guarantee.

## 4. Budgeting Disk Space

### 4.1. Distinguishing `-Xmx`, used heap, and HPROF size

- `-Xmx` is the **maximum heap limit**, not a guaranteed dump size.
- **Used heap** is heap in use at measurement time; a post-full-GC snapshot can differ substantially from pre-GC usage.
- **HPROF file size** depends on object count and types, metadata, references, `-all`, and compression; there is no exact formula "`HPROF = Xmx`."
- With `-gz`, account for both **compressed output** size and whether your analyzer reads it directly or needs another volume to decompress it.

Base estimates on **real dumps from similar workloads** whenever possible. When unavailable, leave a conservative buffer and enforce operational limits; a multiplier like **1.5–2 × `-Xmx` per uncompressed dump** is only an *initial heuristic* for provisioning, **not guaranteed sufficient on every system**. Refine it using actual HPROF measurements, quotas, and real headroom.

Useful budgeting formula:

```text
RequiredFreeSpace =
    (expected concurrent dumps × expected size per dump)
  + space for logs/temp/app during the window
  + safety margin headroom
```

**Example:** A JVM with `-Xmx8g` and no sample dump yet. Pick a conservative assumption of 1.5 × 8 GiB = **12 GiB/dump**. To hold **two** snapshots concurrently and keep **4 GiB** of operational headroom on the volume → reserve at least **28 GiB available** on the target volume (`2 × 12 + 4`). This is an **illustrative budgeting rule**; increase it if measurements, filesystem quotas, or log volume demand more.

### 4.2. Checking the exact volume and limits

On Linux, run checks inside the environment where the **target JVM actually resolves the path**; for instance, assuming the service uses `/srv/heapdumps`:

```bash
df -h /srv/heapdumps
df -i /srv/heapdumps
ls -ld /srv/heapdumps
```

`df -h` shows free bytes on the filesystem and `df -i` shows free inodes; neither **replaces** checking per-user disk quotas, PVC quotas, ephemeral storage limits, platform policies, or space reserved for logs. Free space on the host does not mean a container-mounted volume has space.

When running in containers or Kubernetes:

1. Distinguish paths **inside the container** from paths **on the node/host**; use an absolute path that exists and is writable inside the JVM container.
2. Check whether the volume is an **ephemeral filesystem** or a persistent/attached volume. If the pod is replaced, dumps on ephemeral storage can vanish; plan how to ship files out before pod termination.
3. Account for **ephemeral-storage** limits, quotas, write throughput, and eviction policies. A large file can trigger pod eviction even when the host still has free disk.
4. Schedule transferring the file to dedicated storage; avoid leaving dumps long-term on the same volume used for logs or critical data.
5. With minimal JRE-only Java images, `jcmd` may be absent; prepare appropriate JDK/tooling and attach permissions **before an incident**.

On Windows hosts, inspect the corresponding drive's free space, directory ACLs, and permissions of the Windows service account; for example, `D:\secure-dumps\heap-1234.hprof`. Do not blindly apply `df`, `chmod`, or `sudo` commands.

## 5. Permissions to Create, Read, and Share Dump Files

### 5.1. Three independent permission layers

**(1) Permission to send commands to the JVM.** Per JDK 21 docs, `jcmd` must run on the same machine as the JVM and use matching **effective user and group identifiers** for the Java process. The PID must also be visible within the same environment/process namespace; `jcmd -l` on the host may not list JVMs running in an isolated Docker PID namespace. Some JVMs disable attach via `-XX:+DisableAttachMechanism`.

**(2) JVM permission to write the dump.** The file is created by the target JVM process itself, so the **service account running the JVM** must have create and write permissions in the output directory; the terminal operator's permissions do not automatically grant access to the JVM. The directory must already exist on a volume with sufficient space.

**(3) Analyst permission to read/copy the dump.** Only incident responders assigned to investigate should have access. You may separate the operations team (authorized to trigger dumps) from the analysis team (authorized to read transferred copies).

### 5.2. Preparing the directory on Linux (example)

Suppose the JVM runs under user and group `app`; the administrator prepares:

```bash
sudo install -d -o app -g app -m 0700 /srv/heapdumps
sudo -u app test -w /srv/heapdumps
ls -ld /srv/heapdumps
```

`0700` restricts directory access to the owner; adjust permissions and UID/GID to your environment. Use ACLs if workflows require additional readers. If configuring `umask`, set it on the **service/JVM process at startup**; changing `umask` in the shell invoking `jcmd` does not control permissions on files created by the JVM.

Keep the directory outside public web roots, uncontrolled shared `/tmp`, source code trees, and locations automatically shipped by log forwarders. Enforce **least privilege**, encrypt at rest and in transit, maintain audit trails, and set retention limits. **Never attach HPROF files directly to public tickets, chat channels, or repositories.**

### 5.3. Pre-write verification

- The operator can attach to the right JVM/PID with a matching JDK; the service account can write to the directory.
- The new filename is **unique** to avoid colliding with existing files. `GC.heap_dump` on JDK 21 does **not overwrite** existing files by default; do not pass `-overwrite` casually.
- The directory contains no symlinks or paths redirecting outside approved locations; mounts and ownership match approved config.
- An owner is designated to authorize copying, verify checksums, and delete upon expiration; do not let short-lived diagnostic files become permanent storage.

## 6. Controlled Execution Workflow with `jcmd`

The examples below are **illustrative runbook steps only**. Replace `<PID>`, account, filename, path, and time window with verified values. Run commands **on the host/container owning the JVM**, with valid permissions, after confirming time and disk budgets.

### 6.1. Preflight

```bash
java -version
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.flags
df -h /srv/heapdumps
df -i /srv/heapdumps
```

- `java -version` in the shell is only a reference; `jcmd <PID> VM.version` identifies the target JVM, and `VM.flags` reveals configured heap options.
- Confirm the PID via the service manager or process list, especially in containers. Avoid targeting by main class or PID `0`, which can match **multiple JVMs** when you intend only one process.
- Do not read `GC.heap_info` as a forecast of future HPROF file size; it shows heap statistics at observation time.
- To check exact syntax supported by the target JVM, run `jcmd <PID> help GC.heap_dump`; tooling should match the target's JDK version.

### 6.2. Capturing an uncompressed HPROF

```bash
jcmd <PID> GC.heap_dump /srv/heapdumps/heap-<PID>-20261029T100000Z.hprof
```

The timestamp in the filename is an **example**; replace it with the actual capture timestamp and confirm the file does not yet exist. Use an absolute path; the file is written in the JVM's filesystem namespace, not necessarily on the administrator's local workstation.

Record command start and end times while watching latency, error rate, node I/O, disk space, and health probes throughout the window. Log metadata alongside the artifact—**JDK version, GC, `-Xmx`, PID, instance/pod, timestamp, traffic load, and dump flags**—for accurate interpretation later.

### 6.3. Compression and all-objects options

```bash
jcmd <PID> GC.heap_dump -gz=1 /srv/heapdumps/heap-<PID>-20261029T101500Z.hprof.gz
jcmd <PID> GC.heap_dump -all /srv/heapdumps/heap-<PID>-20261029T103000Z.hprof
```

These are **two separate examples for different goals**, not a recommendation to take three consecutive dumps in production. `-gz=1` writes gzip with a CPU trade-off; `-all` preserves unreachable objects, differing from a post-full-GC reachable snapshot. When using `-all` for retention analysis, remember the object set includes dereferenced objects not yet collected by GC.

**Do not use `-all` or compression merely to skip a maintenance window without measuring their impact first.**

### 6.4. Verifying output and handoff

```bash
ls -lh /srv/heapdumps/heap-<PID>-20261029T100000Z.hprof
stat /srv/heapdumps/heap-<PID>-20261029T100000Z.hprof
sha256sum /srv/heapdumps/heap-<PID>-20261029T100000Z.hprof
df -h /srv/heapdumps
```

Success means **the command returned cleanly, the file exists with reasonable size**, opens in a compatible HPROF analyzer, and the destination checksum matches the source. Never treat any non-zero file as complete proof: a mid-write failure can leave a corrupt or truncated file.

After copying over an approved channel, recompute the checksum at the destination. Delete the source file only after the incident owner confirms readability, successful handoff, and policy compliance. Do not let a heavy copy trigger an I/O spike on the same volume right after the dump.

## 7. Preparing Automatic Capture on `OutOfMemoryError`

Instead of waiting for `OutOfMemoryError` and hoping to run `jcmd` in time, enable both flags at startup (with the path pointing to a pre-created, writable directory):

```bash
java -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/srv/heapdumps/ \
     -Xmx2g -jar app.jar
```

`-XX:+HeapDumpOnOutOfMemoryError` is off by default; `-XX:HeapDumpPath` specifies the dump file or directory. Do not rely on the default working directory, as it is often unclear or non-writable; given an existing directory, HotSpot can auto-name the file using the PID. Verify actual behavior with your exact JDK, container image, and service manager.

Limitations to remember:

- An OOME is not necessarily a Java heap leak; it can result from a heap limit set too low, Metaspace/native resources, or platform memory pressure.
- A JVM or pod killed via **OOMKilled/SIGKILL** can terminate before Java raises OOME and writes a dump.
- If an outage stems from a full disk or volume, the dump file will likely fail to write; flags do not replace capacity planning.
- Automatic dumps occurring **while a system is already failing** can prolong recovery. Account for health checks, restart policies, and artifact preservation.
- If a JVM restarts repeatedly, establish naming, quota, and retention policies so dumps do not accumulate uncontrollably.
- Never intentionally trigger OOME in production as a "config test"; validate in a safe environment first.

## 8. Small Hands-On Lab Runnable on JDK 21

Run the sample program below on a test machine or container; it retains roughly 8 MiB of byte arrays on the Java heap so you can practice taking a dump **with no real sensitive data**.

Create the file **`HeapDumpLab.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class HeapDumpLab {
    private static final List<byte[]> ROOTS = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < 8; i++) {
            ROOTS.add(new byte[1_048_576]);
        }

        System.out.println("READY: retained " + ROOTS.size() + " MiB");
        System.out.println("Press ENTER to exit");
        System.in.read();
        System.out.println("DONE");
    }
}
```

**Terminal A (interactive, keeps the program waiting for input):**

```bash
javac HeapDumpLab.java
java -Xms32m -Xmx64m HeapDumpLab
```

**Program stdout**, after you press ENTER to exit:

```text
READY: retained 8 MiB
Press ENTER to exit
DONE
```

If stdin closes immediately, the program may exit before you capture the dump; run in an interactive terminal. `8 MiB` is the size of the **retained arrays**, not a promise that the HPROF file will be exactly 8 MiB.

**Terminal B (while Terminal A is still waiting):**

```bash
jcmd -l
jcmd <LAB_PID> GC.heap_dump /tmp/heap-lab-unique.hprof
ls -lh /tmp/heap-lab-unique.hprof
```

Replace `<LAB_PID>` with the `HeapDumpLab` PID from the list above; use a unique path in a writable test directory. Measure actual dump duration and HPROF size, and experiment with increasing array counts—no OOME is needed to practice the procedure. **Do not upload this lab file to public services.**

In locked-down environments, prefer creating a dedicated `0700` directory instead of `/tmp`; `/tmp` is used here solely for local practice.

## 9. Approval and Handoff Record Template

Every production dump should have a brief record sufficient for others to reproduce and audit the decision:

| Field | Illustrative example |
| --- | --- |
| Goal / incident | Analyze heap growth after 4 hours under load |
| Service / JVM / GC | `payment-api`, Java 21, G1, verified PID |
| Approver / operator | Responsible on-call and authorized operator |
| Window | 01:00–01:30 UTC after draining traffic |
| Abort threshold | Error rate or latency exceeding agreed threshold |
| Heap / expected dump | `-Xmx8g`; budgeted 12 GiB per dump, to be verified |
| Location / free space | Dedicated volume `/srv/heapdumps`, minimum approved headroom |
| Permissions / classification | Service account writes, analysis group reads copy, sensitive data |
| File / checksum / size | Recorded after successful creation |
| Destination / TTL | Audited private storage, retention per policy |
| Operational outcome | Wall-clock time, p95/p99, error rate, volume usage before/after |

Values in this table are **examples**, not universal defaults. Schedule windows according to actual product calendars and time zones.

## 10. Common Errors and Troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `jcmd` cannot see PID | Different user, container PID namespace, attach permissions, JVM/tool version mismatch | Run in the same environment, check process manager, effective UID/GID, `-XX:+DisableAttachMechanism` |
| Command runs but no file is created | Missing directory, insufficient **JVM** write permissions, duplicate filename, filesystem full/quota | Check owner, mount, `df`, quotas, unique name; read `jcmd` output messages |
| File is tiny or corrupt | Incomplete dump, killed/evicted mid-write, out of disk | Check exit status, logs, size, HPROF parser open test, checksum |
| Dumping causes service timeouts | Full GC, heap size, write contention, too few spare replicas | Measure metrics, drain/rotate replica, rehearse in staging, pick a better window |
| Dump fills logs volume | Shared volume, estimated only from used heap, forgot multiple copies | Use dedicated volume, multiply by copy count, raise headroom, enforce retention |
| `HeapDumpOnOutOfMemoryError` set but no file found | Crash/kill outside Java OOME path, PID changed, unwritable path, out of space | Inspect startup flags, orchestrator events, and filesystem inside the exact pod/host |
| Copied file fails to open | Interrupted transfer, needs decompression, incomplete capture | Compare checksums and size, check HPROF/gzip headers, verify analyzer version |
| Dump exposed in artifacts/tickets | Overbroad sharing, public bucket, automatic backups, default ACLs | Isolate source/dest, encrypt, verify ACLs, revoke access, follow incident response |

A **heap dump does not confirm a leak solely by being large**. Concluding a leak requires time context, retained objects, GC data, and workload/snapshot comparisons. This lesson covers **safe planning and collection**; dominator tree and GC root analysis are the next deeper steps.

## 11. Before, During, and After Checklist

**Before capture**

- [ ] Confirmed goal, JVM/JDK/GC/PID, and representative load timing.
- [ ] Planned service impact, spare replicas, metrics watcher, and abort thresholds.
- [ ] Budgeted *per-dump* size × count, write bandwidth, and headroom; checked volume/quotas in the right namespace.
- [ ] Verified JVM account write access to a dedicated directory and valid operator attach permissions.
- [ ] Agreed on unique filename, transfer destination, encryption, authorized readers, and expiration date.

**During capture**

- [ ] Executed a single command against the verified PID; logged exact start time and options.
- [ ] Monitored p95/p99, errors, CPU, GC, I/O, disk space, and health checks.
- [ ] Logged any anomalies and intervention decisions.

**After capture**

- [ ] Verified command success, file validity, and exact location.
- [ ] Recorded file size, checksum, JVM version, and investigation metadata.
- [ ] Transferred over a secure channel, verified destination checksum, and enforced least-privilege permissions.
- [ ] Monitored recovery of latency/throughput and volume usage.
- [ ] Deleted source/copies once policy conditions are met; archived handoff and closure trail.

## 12. References

- [Oracle JDK 21 — `jcmd`, especially `GC.heap_dump` and `-all`, `-gz`, `-overwrite`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — `java`, `HeapDumpOnOutOfMemoryError`, `HeapDumpPath`, `DisableAttachMechanism`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle JDK 21 — Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html)
- [Oracle JDK 21 — Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html)

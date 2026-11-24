# 6.10 HotSpotDiagnosticMXBean for heap dumps and manageable VM options

## Learning objectives

When investigating a memory leak, analyzing retained objects, or verifying whether a JVM flag can be changed while the application is running, Java provides a dedicated HotSpot management interface: `com.sun.management.HotSpotDiagnosticMXBean`.

The most important point: **even within the same MXBean, not every method is read-only observation**. `getDiagnosticOptions()` and `getVMOption(...)` inspect state; `dumpHeap(...)` writes a potentially large heap dump file that can impact the process; `setVMOption(...)` actively mutates a runtime-adjustable flag. An uncontrolled diagnostic action can alter the very phenomenon being measured.

After completing this lesson, you will be able to:

- Understand the role, module, HotSpot scope, and JMX ObjectName of `HotSpotDiagnosticMXBean`.
- Obtain the MXBean from `ManagementFactory`, look up `VMOption`, and read `name`, `value`, `origin`, and `isWriteable`.
- Distinguish **dynamically changeable VM options** from startup-only flags; know when `setVMOption` can be rejected.
- Explain `dumpHeap(String outputFile, boolean live)`: `live=true/false`, `.hprof` format, path resolution on **the machine running the target JVM**, error conditions, and costs.
- Design a risk-control workflow when capturing heap dumps or modifying flags: right process, disk headroom, sensitive data, baseline, timing, authorization, verification, and restoration.
- Compile and run the Java 17+ example including a **deterministic fixture** mode, a read-only live MXBean mode, and a dump mode **only when explicitly confirmed in a lab**.
- Write diagnostic conclusions with explicit evidence scope; never automatically treat a heap dump as proof of a memory leak or assume every JVM flag is dynamically tunable.

## 1. Where does HotSpotDiagnosticMXBean sit in the MXBean ecosystem?

Standard MXBeans in `java.lang.management` such as `MemoryMXBean` or `ThreadMXBean` provide general management information. `HotSpotDiagnosticMXBean` resides in:

```text
Module:      jdk.management
Package:     com.sun.management
Interface:   HotSpotDiagnosticMXBean
JMX name:    com.sun.management:type=HotSpotDiagnostic
```

This is a **HotSpot VM** diagnostic interface, not a guarantee that every Java VM implementation provides this exact interface or identical options. `com.sun.management` is an extension package supplied by the JDK for HotSpot, unlike pure Java SE calls that every VM must support.

**Three layers to distinguish:**

| Layer | Components | What can it do? |
| --- | --- | --- |
| In-app API | `HotSpotDiagnosticMXBean`, `VMOption` | Read flags, write heap dumps, and adjust permitted flags |
| JMX management | Platform MBeanServer, ObjectName `com.sun.management:type=HotSpotDiagnostic` | Management clients access operations when connected/authorized |
| Inside HotSpot | VM flags, memory manager, heap dump implementation | Performs the actual state change or heavy operation |

To obtain the interface in Java 17, commonly use:

```java
import com.sun.management.HotSpotDiagnosticMXBean;
import java.lang.management.ManagementFactory;

HotSpotDiagnosticMXBean bean =
        ManagementFactory.getPlatformMXBean(
                HotSpotDiagnosticMXBean.class);
```

This is an integrated snippet, not a standalone program; complete usage appears in the lab section. If the environment does not support this HotSpot MXBean, do not infer from `null` or a startup error that heap behavior itself is broken. Record the JVM vendor, version/patch, and actually available APIs.

**Remote JMX:** the same bean can appear in the platform MBeanServer. Administrators using JMX can read attributes or invoke `dumpHeap` or `setVMOption` if permitted. **Remote invocation does not mean the dump is downloaded to the client**: the dump is written on the filesystem visible to the **target JVM**. Connection security and operation authorization are separate concerns that must be controlled.

## 2. Classifying the four main methods by actual impact

Java 17 provides four main methods:

| Method | Operation kind | Result / effect | Notes |
| --- | --- | --- | --- |
| `getDiagnosticOptions()` | Observation | List of dynamically adjustable diagnostic `VMOption`s | Not a list of **all** JVM flags |
| `getVMOption(name)` | Observation | One `VMOption` by name if it exists | May return a **non**-writable flag; unknown name → exception |
| `setVMOption(name,value)` | **Intervention** | Requests changing an option allowed by the JVM at runtime | Check `isWriteable`, valid value, permissions, side effects |
| `dumpHeap(outputFile,live)` | **Intervention / heavy artifact** | Creates an HPROF heap dump file | Pause/GC/I/O, disk, sensitive data, target path |

Read methods still carry management interface invocation cost; however, the main risks lie in **dumping large heaps** and **mutating flags on a live process**.

Never call `setVMOption` just to "test whether a flag exists"; use `getVMOption` for read checks. Never call `dumpHeap` when you only need heap used/max; start with `MemoryMXBean`, GC logs, metrics, or already-enabled tooling.

## 3. VMOption: name, value, writeable, and origin

`com.sun.management.VMOption` describes a VM option value at snapshot time.

```java
VMOption opt = bean.getVMOption("SomeOptionName");

String name = opt.getName();
String value = opt.getValue();
boolean canChangeNow = opt.isWriteable();
VMOption.Origin origin = opt.getOrigin();
```

This is **integrated illustrative code**. `SomeOptionName` is a placeholder name to explain the API signature; never run that literal string in production. Use a flag name verified on the target JVM.

### 3.1 Meaning of each field

- `getName()`: option name recognized by HotSpot.
- `getValue()`: **string value at the moment the `VMOption` object was created**, not a live binding that updates when the flag changes.
- `isWriteable()`: JVM indicates the option **can be dynamically set via the management interface**. The API spells it **`Writeable`**, not `Writable`.
- `getOrigin()`: source of the value at snapshot time, distinguishing default flags from those coming from command line, config files, or management changes.

A `VMOption` returned prior to a change does not automatically update its `value` after `setVMOption`; you must **call `getVMOption` again** for a fresh snapshot.

### 3.2 `VMOption.Origin` values in Java 17

| Origin | Meaning |
| --- | --- |
| `DEFAULT` | Option has not been set; using default |
| `VM_CREATION` | Set at VM creation (typically launcher args / JNI invocation) |
| `ENVIRON_VAR` | Set via environment variable |
| `CONFIG_FILE` | Set via configuration file |
| `ERGONOMIC` | Chosen by the VM through ergonomic auto-tuning |
| `MANAGEMENT` | Modified through the management interface after VM startup |
| `ATTACH_ON_DEMAND` | Set via the attach framework |
| `OTHER` | Came from another mechanism |

Origin **is not a check of whether a flag is operationally appropriate**. For example, `VM_CREATION` only tells you the flag was set at startup, not that it is optimal. `MANAGEMENT` shows the value came via a management interface, not that the change improved the symptom.

### 3.3 `getDiagnosticOptions` is not the entire `-XX` list

Per Java 17 Javadoc, a "diagnostic option" in this API is a **writeable VM option that can be set dynamically** for diagnostic purposes. The list:

```java
List<VMOption> manageable = bean.getDiagnosticOptions();
```

only covers that API-defined subset; it neither replaces the full effective VM flags output of `jcmd VM.flags -all` nor proves a flag absent from the list does not exist.

`getVMOption(name)` lets you look up a flag by name and read `isWriteable()`, even when that flag is not in the writable diagnostic list. If the name does not exist, `IllegalArgumentException` simply means "option not present on the running VM", not that the entire Java application is broken.

When building automation tools, **never hard-code one JDK version's writable flag list** and apply it across all builds. `-XX` flags can change or disappear across JDK versions, vendors, OSes, collectors, or runtime options.

## 4. Heap dump via `dumpHeap(String outputFile, boolean live)`

Method signature:

```java
void dumpHeap(String outputFile, boolean live)
        throws IOException;
```

Creates a file in **HPROF heap dump** format, containing object/reference graph information in the Java heap. This file enables analyzing object counts, retained sizes, dominator trees, and retaining paths with suitable tools.

### 4.1 `live=true` vs. `live=false`

| Value | Requested object set | Suitable analysis |
| --- | --- | --- |
| `live=true` | Objects currently **reachable** from roots/other objects per API semantics | Analyzing retained objects, memory retention |
| `live=false` | Includes **even unreachable objects** at capture time as supported by the VM | Broader allocation/heap content investigation, keeping in mind uncollected garbage may be included |

"Live" here means **reachable**, **not** "recently touched by a request within the last minute" or "never a leak". A leak in Java is typically **objects that remain reachable yet are no longer needed by the business logic**.

**Critical detail:** to determine the reachable object set and capture a consistent snapshot, creating a dump can force the JVM to synchronize/pause and/or perform GC work depending on the collector/implementation. With `live=true` in HotSpot, operators should prepare for possible GC activity and latency impact. Never call a heap dump "side-effect-free read-only" just because the method does not mutate application objects.

`live=false` **does not** guarantee "no pause", "no synchronization", or "fast dump"; it only changes which objects are requested in the artifact. When comparing two dumps, record **both the `live` flag and timestamp** because data characteristics differ.

### 4.2 Where is the file written?

Java 17 Javadoc specifies:

- When called **directly in-process**, `outputFile` is resolved on the filesystem visible to that JVM process.
- When called **from a JMX client on another process/machine**, the dump is still written **on the target JVM's machine**, not on the client machine.
- If a **relative path** is used, it resolves against **the target VM's startup working directory**.
- The dump file must have the **`.hprof` suffix** and a valid filename for the OS/VM.

Hence in containers/Kubernetes, `/tmp/app-heap.hprof` lands inside the **Java container's** filesystem, not the operator's `/tmp`. If the target container restarts, ephemeral artifacts can vanish; plan extraction and security handling. A path existing on the monitoring host **does not** prove that path is writable inside the target container.

**Practical rule:** prefer an absolute path with verified permissions/headroom on **the exact target filesystem**, a unique filename carrying run/PID/timestamp, and secure retrieval procedures. Never guess target paths from the client machine.

### 4.3 Errors to recognize

Per Java 17 Javadoc:

| Condition | Possible exception | What to check |
| --- | --- | --- |
| Target file already exists or cannot be created/opened/written | `IOException` | Unique name, directory, permissions, disk/quota, mount, inodes |
| Filename does not end with `.hprof` | `IllegalArgumentException` | Supply exact suffix |
| `outputFile == null` | `NullPointerException` | Never pass `null` |
| Unsupported operation | `UnsupportedOperationException` | JVM/vendor/implementation and environment |
| Management/file write permission denied under appropriate security config | `SecurityException` | Caller permissions, management policy, filesystem permissions |

If disk space is insufficient, **do not invoke the dump** rather than risking filling the disk while the service is already degraded. Checking free space beforehand is a risk check, not a guarantee the final file will fit, since heap and free space can fluctuate.

A dump's size can approach or exceed currently used heap depending on format/object contents/metadata and write mechanism. Do not rely on a rigid formula like "file = Xmx" as a capacity guarantee. Furthermore, disk pressure and I/O amplification can hurt the running service itself.

### 4.4 HPROF files can contain sensitive data

A heap dump is not a field-redacted log. It can contain:

- Request/response payloads, customer/session identifiers, emails, addresses, and business records.
- Tokens, secrets, and passwords/strings still residing on the heap depending on application handling.
- Buffers, caches, connection strings/URIs, and confidential internal data.
- Object graphs/reference structures that reveal internal architecture.

Enforce access control, encryption at rest/in transit when transferring files, clear lifecycle/retention, non-public storage, minimal copying, and deletion after expiration. Never commit HPROF files or stacks/metadata containing real data to public chats or repositories.

## 5. Distinguishing `dumpHeap` from `jcmd GC.heap_dump`

Both typically serve to capture a heap dump from HotSpot, yet they are **two different interfaces**.

| Perspective | `HotSpotDiagnosticMXBean.dumpHeap` | `jcmd <PID> GC.heap_dump` |
| --- | --- | --- |
| Invocation point | From Java code or over JMX | CLI / attach diagnostic command |
| Object scope parameter | `live=true/false` | Options such as `-all` in JDK 17 |
| Output target | `outputFile` on target JVM filesystem | File path handled by target JVM |
| Behavior | Snapshot may affect GC/pause/I/O | JDK 17 docs note it requests a full GC by default unless `-all` is passed |
| Permissions | Management/JMX/OS permissions | Attach permission on target process |
| Risks | Large HPROF file, privacy, altering observed state | Similar risks; check exact help/version |

Do not assume `live=false` or `-all` is a "zero-GC, zero-pause" option. GC mechanics, synchronization, and snapshot cost depend on VM build, collector, heap size, and workload. Rely on documentation for your exact JDK and actual context.

When you **only need heap usage**, `MemoryMXBean.getHeapMemoryUsage()` and existing GC metrics/JFR are far less invasive than a heap dump. Only take a dump when the question requires object graphs/retaining paths that aggregate metrics cannot answer.

## 6. `setVMOption`: mutating dynamically, not reading

Method signature:

```java
void setVMOption(String name, String value);
```

Requests the JVM to modify a runtime-tunable option. The value is passed as a **String**, even when the option represents a boolean, integer, size, or another type. Only values accepted by the VM are valid.

**Minimum sequence before changing:**

1. Verify the exact **process/JVM/vendor/version/build/PID**.
2. Read `getVMOption(name)` and record `value`, `origin`, and `isWriteable`.
3. If `isWriteable()==false`, **do not** attempt setting it "just to see what happens".
4. Identify what the change impacts: logging, error handling, diagnostics, performance, or security.
5. Define scope, blast radius, window, owner, and rollback plan.
6. Only after authorization, call `setVMOption(name,newValue)` in the right environment/session.
7. Call `getVMOption(name)` **again**, verify effective value and origin, and monitor real metrics/state.
8. If rollback is needed, follow the policy for that flag, then **re-read** and verify side effects (files/logs/recordings may not revert merely because the flag was reset).

**Integrated code example — not executed automatically in the lab:**

```java
// Preconditions: owner approved the specific flag/change;
// name and newValue already validated for this JVM.
VMOption before = bean.getVMOption(name);
if (!before.isWriteable()) {
    throw new IllegalStateException(
            "VM option cannot be changed dynamically: " + name);
}

String originalValue = before.getValue();
// Record timestamp, PID, originalValue and expected impact.
// bean.setVMOption(name, newValue);       // MUTATING: deliberately disabled.
// VMOption after = bean.getVMOption(name); // Re-read if a change was approved.
```

This is an **integrated illustrative snippet**, not standalone, and intentionally **does not execute the set call**. Uncommenting it in production requires validating the specific flag and operational authorization. Saving the initial value is essential, yet do not assume rolling back via `setVMOption(name,originalValue)` undoes every side effect outside the VM flag (such as written files or altered log output).

### 6.1 Flag "manageability" does not mean everything is tunable

- Some flags apply only at JVM startup, like many core heap/collector settings; you cannot turn `-Xmx` into a dynamic change just via the management API.
- `-XX` flags have no stability guarantee across every major JDK/vendor.
- `getDiagnosticOptions()` lists options supporting dynamic diagnostic tuning; do not use it to assert that **any** flag missing from the list does not exist.
- `getVMOption` reports value and writeability **at read time**; runtime conditions may change afterward.

When setting an option that **does not exist**, is **non-writeable**, or has an **invalid value**, Javadoc specifies `IllegalArgumentException`. If `name` or `value` is null, `NullPointerException`; an environment with appropriate security/permission controls may throw `SecurityException`.

### 6.2 Why distinguish `value` and `origin`?

Suppose an option at T1 has `value=false`, `origin=DEFAULT`, `writeable=true`. After a valid adjustment at T2, a **new `VMOption` object** may show `value=true`, `origin=MANAGEMENT`.

**Do not** expect the earlier `before` object to update itself. It holds the earlier snapshot per Javadoc. If an app or monitoring tool caches the old object, dashboards can display stale info; timestamp every sample.

Origin also helps investigate discrepancies between manifests/JVM args and running state: a flag may have been changed post-startup via management or attach. However, you need event/audit logs to know **who** changed it and why; `Origin` is not a complete audit trail.

## 7. Java 17+: lab program with safe-by-default modes

The program below provides three modes:

1. **`fixture`**: constructs two simulated `VMOption` instances via the standard constructor, distinguishing writeable and non-writeable flags, printing deterministic stdout. This mode **neither reads nor modifies flags on the running JVM**.
2. **`inspect`**: reads the **lab JVM's** HotSpot MXBean, prints the ObjectName and diagnostic option count; writes no dump and mutates no flags. You may optionally pass a flag name to inspect its live value; output depends on the JDK and live flags.
3. **`dump-lab`**: writes a heap dump **only when the learner explicitly passes a full path and confirmation string**, inside **a dedicated lab JVM**. There is no automated `setVMOption` mode to prevent accidental runtime configuration edits.

Create the file **`HotSpotDiagnosticLab.java`**:

```java
import com.sun.management.HotSpotDiagnosticMXBean;
import com.sun.management.VMOption;
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;

public class HotSpotDiagnosticLab {
    private static HotSpotDiagnosticMXBean bean() {
        HotSpotDiagnosticMXBean result =
                ManagementFactory.getPlatformMXBean(
                        HotSpotDiagnosticMXBean.class);
        if (result == null) {
            throw new IllegalStateException(
                    "HotSpotDiagnosticMXBean unavailable");
        }
        return result;
    }

    private static String describe(VMOption option) {
        return option.getName()
                + " value=" + option.getValue()
                + " writeable=" + option.isWriteable()
                + " origin=" + option.getOrigin();
    }

    private static void fixture() {
        VMOption fixed = new VMOption(
                "ExampleFixed", "512m", false,
                VMOption.Origin.VM_CREATION);
        VMOption dynamic = new VMOption(
                "ExampleDynamic", "false", true,
                VMOption.Origin.DEFAULT);

        System.out.println(describe(fixed));
        System.out.println(describe(dynamic));
        System.out.println(
                "heapDump: file must end with .hprof");
        System.out.println(
                "live=true: reachable objects only");
        System.out.println(
                "setVMOption: mutates a writeable VM option");
    }

    private static void inspect(String name) {
        HotSpotDiagnosticMXBean mx = bean();
        System.out.println("objectName=" + mx.getObjectName());
        List<VMOption> options = mx.getDiagnosticOptions();
        System.out.println("diagnosticOptionCount=" + options.size());

        options.stream()
                .sorted(Comparator.comparing(VMOption::getName))
                .limit(5)
                .forEach(opt -> System.out.println(
                        "manageableName=" + opt.getName()));

        if (name != null) {
            try {
                VMOption opt = mx.getVMOption(name);
                System.out.println("requested=" + describe(opt));
            } catch (IllegalArgumentException exception) {
                System.out.println("optionNotFound=" + name);
            }
        }
    }

    private static void dumpLab(String filename, String confirmation)
            throws IOException {
        if (!"I_UNDERSTAND_THE_RISK".equals(confirmation)) {
            throw new IllegalArgumentException(
                    "explicit confirmation required");
        }

        Path target = Path.of(filename).toAbsolutePath().normalize();
        if (!target.toString().endsWith(".hprof")) {
            throw new IllegalArgumentException(
                    "target must end with .hprof");
        }
        if (Files.exists(target)) {
            throw new IllegalArgumentException(
                    "refuse to use an existing file");
        }
        if (!Files.isDirectory(target.getParent())) {
            throw new IllegalArgumentException(
                    "parent directory does not exist");
        }

        // Writes HPROF on THIS JVM's filesystem. May pause/cause GC.
        bean().dumpHeap(target.toString(), true);
        System.out.println("heapDumpWritten=" + target);
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("fixture")) {
            fixture();
            return;
        }
        if ((args.length == 1 || args.length == 2)
                && args[0].equals("inspect")) {
            inspect(args.length == 2 ? args[1] : null);
            return;
        }
        if (args.length == 3 && args[0].equals("dump-lab")) {
            dumpLab(args[1], args[2]);
            return;
        }
        System.out.println(
                "Usage: java HotSpotDiagnosticLab "
                + "fixture|inspect [flag]|dump-lab <file.hprof> "
                + "I_UNDERSTAND_THE_RISK");
    }
}
```

### 7.1 Compile/run deterministic mode

Use **JDK 17 HotSpot** or a compatible JDK 17 build with `jdk.management`:

```bash
javac HotSpotDiagnosticLab.java
java HotSpotDiagnosticLab fixture
```

**Exact stdout** of `fixture`:

```text
ExampleFixed value=512m writeable=false origin=VM_CREATION
ExampleDynamic value=false writeable=true origin=DEFAULT
heapDump: file must end with .hprof
live=true: reachable objects only
setVMOption: mutates a writeable VM option
```

Explanation:

- `ExampleFixed` and `ExampleDynamic` are **simulated VMOptions** built with the constructor, **not** two pre-existing HotSpot flags.
- `isWriteable` and `Origin` print the exact values passed in.
- No `bean().dumpHeap` or `bean().setVMOption` call runs in `fixture` mode.
- Because it does not touch live heap or flags, stdout is independent of JVM arguments or machine load.

### 7.2 Read-only mode against the live JVM

```bash
java HotSpotDiagnosticLab inspect
```

This prints the bean's ObjectName, diagnostic option count, and up to five option **names** alphabetically. There is no fixed stdout because option counts/names depend on the JDK/build and option availability.

If you have verified a flag name present on the lab JVM:

```bash
java HotSpotDiagnosticLab inspect HeapDumpOnOutOfMemoryError
```

This is a **lookup example**, not an assertion that every HotSpot build must expose that name. If the flag does not exist, the program prints `optionNotFound=...`. If it exists, it prints `value`, `writeable`, and `origin`. **Never send output containing configuration secrets to public channels**.

**Note:** each `java HotSpotDiagnosticLab ...` invocation launches **a new JVM**. It reflects the lab JVM's own settings, **not** another running Java service even on the same machine. For a real service, you need a JMX connection to the right target or another authorized diagnostic channel.

### 7.3 Intentional dump mode

Run only in an **authorized lab environment**, after checking disk space, target directory, and retention:

```bash
java HotSpotDiagnosticLab dump-lab ./lab-heap.hprof I_UNDERSTAND_THE_RISK
```

This command starts a new lab JVM, writes a heap dump of **itself** with `live=true`, and prints the full path. **Exact stdout cannot be predicted** because absolute paths, file operations, and VM state depend on the machine. If the file already exists, the program intentionally refuses instead of overwriting. The program is still subject to `IOException` or other errors if the filesystem disallows writing.

Do not run this on production data just as an exercise: HPROF files can contain sensitive heap contents and grow large. The confirmation string only prevents accidental calls in the lab; **it does not replace operational authorization, security policy, or resource preflight checks**.

### 7.4 Running on a JVM without the HotSpot bean

`fixture` mode uses only the `VMOption` constructor. `inspect` and `dump-lab` require `HotSpotDiagnosticMXBean` to be available. If the JDK runtime lacks the `jdk.management` module or the JVM does not support the interface, use appropriate alternative tools rather than calling this API and blaming the application.

## 8. When calling via JMX: critical differences

ObjectName of HotSpotDiagnosticMXBean:

```text
com.sun.management:type=HotSpotDiagnostic
```

From a compatible JMX client, you can invoke `dumpHeap` or `setVMOption` over `MBeanServerConnection`. However, **remote JMX management must be strictly secured**:

- Enforce authentication, encrypted transport, firewall/allowlists, and least privilege per deployment environment.
- Never open a remote JMX port to the Internet just to run heap dumps.
- Connect strictly to the right JVM instance; across container/pod restarts, identify targets by deployment, PID, and start time.
- Never put credentials into logs or command lines readable by others.
- Control systems may need audit/change-management gates; a "read" JMX client could also invoke **mutating** operations if granted overly broad permissions.
- The `dumpHeap` file is created **on the target VM**, and does not automatically appear on the remote operator's machine. Plan secure artifact transfer/storage.

Conceptual example given an already established, valid `MBeanServerConnection connection`:

```java
HotSpotDiagnosticMXBean remote =
        ManagementFactory.newPlatformMXBeanProxy(
                connection,
                "com.sun.management:type=HotSpotDiagnostic",
                HotSpotDiagnosticMXBean.class);

VMOption current = remote.getVMOption("SomeVerifiedFlag");
```

This snippet is **integrated** code, not standalone: `connection` must come from an authenticated JMX client, and `SomeVerifiedFlag` must be a valid flag. Because this is remote management, handle network timeouts, disconnects, pod/target shifts, permissions, and all communication failures.

Do not spin up a remote JMX server in exercises just to demo this: misconfiguration can open an attack surface.

## 9. Workflow for choosing the least invasive diagnostic method

Before acting, ask: **Do I want to inspect configuration, measure heap pressure, or analyze the object graph?**

### 9.1 When you only need to verify flags

- Collect JDK vendor/version, `VM.command_line`, runtime arguments, and build.
- Read `getVMOption(name)` for known names, recording `value/writeable/origin`.
- If you need the list of manageable options, read `getDiagnosticOptions()`.
- Do not change flags. If you suspect a flag changed post-startup, cross-check `origin` with management audit logs/timelines.

You do not need a heap dump to answer "What is `-Xmx` set to?" or "Is this flag writable?".

### 9.2 When memory usage or GC looks abnormal

- Start with `MemoryMXBean`, per-pool metrics, GC logs/JFR, container memory/RSS, allocation rate, and post-GC occupancy.
- Check whether behavior is steady or just normal GC sawtooth; look for dependency/workload/memory pressure.
- Only if you need **object counts, dominators, or retaining paths**, schedule a heap dump at a representative moment.
- Record `live`, VM version, GC collector, workload, heap size, and capture timestamp. Avoid using a single snapshot to assert a long-term leak.

### 9.3 When testing a VM option adjustment

- Formulate a hypothesis along with predefined metrics and guardrails.
- Verify `isWriteable()` and the flag's semantics on the current JDK version.
- Secure owner/approval, scope boundaries, and canary/rollback plans if in production.
- Capture a baseline, make **one change**, re-read the flag, and measure under equivalent load.
- Record side effects and recovery status. Never equate a successful `setVMOption` call with having fixed the root cause.

## 10. Example investigation of rising heap with gated decisions

Suppose service `checkout` runs a HotSpot JVM with `-Xmx2g`, and post-GC heap `used` climbs from 900 MiB to 1.7 GiB over several hours. These are **hypothetical numbers** for practicing reasoning.

**Phase A — Non-intrusive observation**

- Collect time series of post-GC heap, allocation rate, request mix, cache stats, transaction volume, container memory, and GC pauses.
- Check whether the application recently grew cached data or active sessions.
- Read necessary flags via `getVMOption` without mutating values.
- Cross-check heap `used` against metaspace/direct/native/RSS; container OOM can occur even before heap reaches `Xmx`.

**Phase B — Planning the dump**

If retaining paths are needed, decide timing, target path, `live=true` vs. `false`, disk/quota headroom, permissions, pause risk, and request latency impact.

**Phase C — Controlled dump**

At the approved time, invoke `dumpHeap` on the target VM and record the timestamp. Watch GC/pauses/I/O before and after. Do not run multiple concurrent dumps or change multiple flags simultaneously, or attribution becomes impossible.

**Phase D — Analysis**

Use an HPROF analyzer to inspect large retained objects, dominators, and reference paths to GC roots, and verify **business lifecycle**: should those objects still be held? Compare against another dump with the **same method**, workload, and post-GC checkpoint for growth evidence. Seeing one large `HashMap` is not enough to prove a leak, since a cache may be intentional.

**Phase E — Scoped conclusion**

Write: "At T2, a `live=true` dump showed a set of objects still reachable and occupying most of the heap; retaining paths lead to cache X. Multi-point data and cache lifecycle checks are still needed to confirm unnecessary retention." Do not write: "The heap dump proved all memory pressure is caused by bug X" without cross-checking native memory, workload, and controls.

## 11. Investigating a JVM option that differs from expectations

Example: the manifest declares an option at startup, yet `getVMOption` at runtime shows a different value.

Workflow:

1. Verify the **exact process** and build; Kubernetes may have created the pod from a different revision.
2. Read `VMOption.getValue()` and `getOrigin()`; record the timestamp.
3. Cross-check command line, environment, cgroup/resource policies, JDK ergonomic flags, and management/attach audit logs.
4. Check whether the option is writeable and whether it was altered at runtime; `MANAGEMENT` or `ATTACH_ON_DEMAND` is a clue, though **does not itself identify who made the change**.
5. If performance impact is suspected, run a controlled comparison keeping workload/other settings equivalent and measuring guardrails.
6. Report conclusions, owner, and a plan to persist the change via config/deployment if truly needed. Changing a flag through management **does not edit deployment manifests**; a JVM restart can revert it to another setting.

Never assume every dynamic runtime flag is a long-term supported configuration. HotSpot diagnostic flags can carry side effects, compatibility caveats, or version-specific limits.

## 12. Risk-control matrix for `dumpHeap` and `setVMOption`

| Check | Before `dumpHeap` | Before `setVMOption` |
| --- | --- | --- |
| Right target | JVM/heap/container/PID, desired snapshot time | JVM/flag/version, baseline value |
| Genuine need | Need object graph; lighter metrics insufficient | Clear hypothesis/success criteria and needed change |
| Resources | Heap size, disk/quota, I/O, pause/GC headroom | CPU, latency, log volume, GC/other side effects |
| Permissions | Target file write, JMX/OS permissions | Runtime flag change permission, owner/change approval |
| Parameters | Absolute `.hprof`, `live`, unique filename | `name/value`, `isWriteable`, valid value |
| Sensitive data | HPROF may hold secrets; encrypted storage/access | Runtime config may expose info or alter logging |
| Verification | File exists/readable, right timestamp, size, GC events | Fresh `getVMOption` snapshot, origin, metric guardrails |
| Recovery | Controlled artifact cleanup, keep needed evidence | Verified rollback; avoid assuming every side effect reverts |
| Reporting | Dump run ID/path/live/size/impact | Before/after/owner/metrics/inference limits |

**An easily overlooked detail:** writing a dump is not a "code change", yet it can alter natural heap baselines via GC or pauses. Changing a flag is not a "new deploy", yet it can make profiling results incomparable with earlier runs.

## 13. When to use other tools?

`HotSpotDiagnosticMXBean` is one piece of the toolkit:

| Need | Suitable tool | Limitations |
| --- | --- | --- |
| Periodic heap used/committed/max | `MemoryMXBean` and metrics | Gives no retaining paths |
| GC behavior / pause times | GC logs, JFR, GC MXBeans | Requires setup and collector understanding |
| Object retention paths, dominators | HPROF via MXBean/jcmd, analyzed with heap analyzer | Heavy snapshot, sensitive data |
| Native memory | NMT via `jcmd` when enabled at startup | Does not cover all native allocations |
| Top threads and contention | `ThreadMXBean`, `jcmd Thread.print`, JFR | Snapshot cost and metric limits |
| Full VM flags | `jcmd VM.flags -all`, startup flag output | Should not be treated as all dynamically tunable flags |
| Specific manageable VM option | `HotSpotDiagnosticMXBean.getVMOption` | Flag may be missing on other VMs/JDKs |
| Changing a manageable VM option | `HotSpotDiagnosticMXBean.setVMOption` | **Mutating**; control like an operational config change |

Do not call `HotSpotDiagnosticMXBean` to find deadlocks: dedicated APIs like `ThreadMXBean.findDeadlockedThreads()` serve that purpose. Do not use a heap dump to measure CPU bottlenecks. Match the tool to the diagnostic question.

## 14. Operation and evidence report template

```text
CONTEXT
- Service, environment, JVM vendor/version/patch, process ID:
- Container/pod/node, deployment/build revision:
- Symptom, request/workload, timezone, and timestamp:

OBSERVATION BEFORE
- Heap/GC trend, RSS/container memory, latency/errors:
- Relevant VM option name/value/writeable/origin:
- Reason lighter diagnostics were insufficient:

PROPOSED ACTION
- Read-only getVMOption/getDiagnosticOptions OR
  dumpHeap(outputFile,live) OR setVMOption(name,newValue):
- Approved owner/operation window/rollback authority:
- Expected GC/pause/CPU/I/O/security effects:
- File path on target VM, disk headroom, retention/access policy:

EXECUTION
- Exact command/API, parameters, timestamps, result/errors:
- For dump: path/size/access/hash if required:
- For flag change: before and after VMOption snapshots:

FOLLOW-UP
- JVM/cgroup/latency/GC metrics after action:
- What is confirmed, supported but uncertain, or untested:
- Alternative explanations, workload/measurement limitations:
- Cleanup of HPROF/recordings/config restoration:
- Next controlled test, owner, verification criteria:
```

Never let secret-bearing `VMOption.getValue()` strings or sensitive HPROF paths enter unprotected log pipelines. Reports are part of the diagnostic workflow, not a replacement for primary evidence.

## 15. Common mistakes

1. **Calling `dumpHeap` like reading a lightweight counter.** It can be a heavy operation impacting GC/pause/I/O.
2. **Confusing `live=true` with "only objects currently handling requests".** The definition is reachable objects; a misbehaving cache keeps objects reachable.
3. **Assuming `live=false` means a pause-free dump.** It changes which objects are written, without guaranteeing low overhead.
4. **Invoking heap dump over remote JMX and looking for the file on the client machine.** The file is written on the target VM's filesystem.
5. **Using a relative path without knowing the target's working directory.** It may land in the wrong place or fail to write.
6. **Skipping disk/quota checks and treating HPROF like ordinary logs.** Large files can fill disks and contain sensitive data.
7. **Assuming dump always overwrites an existing file.** Java 17 Javadoc specifies `IOException` when `outputFile` already exists.
8. **Using a filename without `.hprof`.** The API requires the suffix and may reject it with `IllegalArgumentException`.
9. **Treating `getDiagnosticOptions()` as the list of all JVM flags.** It lists only the writable diagnostic subset.
10. **Confusing `VMOption.isWriteable()` with "useful flag" or "no side effects".** Writeable only indicates dynamic mutability.
11. **Calling `setVMOption` before reading/recording the original value.** Loses the rollback baseline and can skew measurements.
12. **Calling `setVMOption` on a non-writeable flag.** `IllegalArgumentException` is not an application bug.
13. **Expecting a `VMOption` object to self-update after a set call.** Its value is a snapshot; call `getVMOption` again.
14. **Seeing `origin=MANAGEMENT` and claiming you know who changed it.** Origin is not an audit log.
15. **Changing multiple flags and taking dumps in the same window without a timeline.** Makes isolating each intervention's impact impossible.
16. **Inferring "no memory leak" from one small heap snapshot.** The dump may have been taken at the wrong time, post-GC, under low load, or without comparing retained growth.
17. **Confusing heap memory with total process/container memory.** JNI/native, direct buffers, metaspace, thread stacks, and page cache also consume resources.
18. **Exposing unauthenticated remote JMX to the network.** Diagnostic operations can write huge files or mutate VM options.
19. **Using figures from another JDK to infer flag semantics on the current JVM.** HotSpot flags can change across vendors/builds/major versions.
20. **Treating a successful `setVMOption` call as a completed fix.** Verify effectiveness under load, correctness, error rate, guardrails, and persistence across restarts.

## 16. Self-check questions

1. Which module/package does `HotSpotDiagnosticMXBean` belong to, and what is its exact JMX ObjectName?
2. How does `getVMOption(name)` differ in scope from `getDiagnosticOptions()`? Why do neither replace the full output of `jcmd VM.flags -all`?
3. What distinct information do `VMOption.getValue()`, `isWriteable()`, and `getOrigin()` provide?
4. Why must you call `getVMOption(name)` again after `setVMOption(name,newValue)`? Does the old `VMOption` object change?
5. What object sets do `dumpHeap(path,true)` and `dumpHeap(path,false)` request? Can `false` be used to guarantee no pause occurs?
6. When a JMX client runs on machine A and the target JVM runs on machine B, where does the HPROF file appear?
7. What errors can `dumpHeap` raise if the file already exists or the filename lacks `.hprof`?
8. Why is `isWriteable=true` still insufficient to conclude "we should tweak this flag immediately in production"?
9. In a container with a 1 GiB memory limit and 600 MiB Java heap used, can it still be OOMKilled? Which other memory areas must be measured?
10. A heap dump shows many objects belonging to one cache. What additional evidence is needed to confirm the cache is retaining unneeded objects?
11. If `VMOption.getOrigin()==MANAGEMENT`, do you already know who made the change? What else must be checked?
12. Describe a **read first → verify permissions/resources → controlled action → re-read → measure guardrails → handoff and cleanup** workflow for a scenario requiring a heap dump.

## References

- Oracle Java SE 17 — `HotSpotDiagnosticMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html
- Oracle Java SE 17 — `VMOption`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/VMOption.html
- Oracle Java SE 17 — `VMOption.Origin`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/VMOption.Origin.html
- Oracle Java SE 17 — `jcmd`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html

**Remember:** `HotSpotDiagnosticMXBean` lets you **read VM options**, **write an HPROF of the Java heap**, and **modify certain manageable options**. Distinguish read operations from artifact-creating or runtime-mutating operations; understand `live`, `isWriteable`, and `origin`; protect dump data and control interventions. A successful API result is technical evidence within its scope—it does not automatically prove the cause of a memory leak or that an incident is resolved.
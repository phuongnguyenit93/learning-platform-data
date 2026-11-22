# Attaching to a JVM Using `VirtualMachine.attach` with a Verified Identifier

> **Goal:** Connect in a controlled manner to **the exact running JVM** using the Java Attach API (`jdk.attach`), based on an identifier verified before calling `VirtualMachine.attach(...)`. This lesson clarifies `id`/PID/`VirtualMachineDescriptor`, identity verification steps, when to attach and detach, a runnable Java 17+ experiment, common pitfalls when multiple JVMs share the same name, and technical limitations of the attach mechanism.

## 1. The problem: knowing the PID does not guarantee knowing the right JVM

On a single host, the following may exist simultaneously:

```text
PID 3180  java -jar orders-service.jar        (staging environment)
PID 4921  java -jar orders-service.jar        (production environment)
PID 7314  java -jar worker-service.jar
```

If a tool receives a string `"4921"` and immediately calls `VirtualMachine.attach("4921")`, it is assuming that PID is the exact JVM it intends to work with. This assumption can fail if the operator copied the wrong PID, if two JVMs have the same command line, if a container has a different PID namespace, or if the old process exited and the OS **reused the PID**.

For instrumentation tools, target-selection errors are especially severe: the step after attach may read information from the wrong application or ask the JVM to load an agent. Therefore, before attaching you must **verify the target's identity from independent evidence**, and immediately after attaching you must perform further checks before executing any impactful operation.

**This lesson focuses on attaching by a verified identifier.** The experiment only reads one system property from the target JVM and then calls `detach`; it does not call `loadAgent` and does not transform bytecode.

## 2. What does the Attach API actually do?

The JDK provides the **`jdk.attach`** module and the `com.sun.tools.attach` package. The central class is `VirtualMachine`.

- `VirtualMachine.list()`: returns a list of `VirtualMachineDescriptor` instances that the installed attach providers can enumerate.
- `VirtualMachineDescriptor.id()`: an **implementation/provider-dependent** identifier; on many JVMs on common operating systems, this value is the PID as a string.
- `VirtualMachineDescriptor.displayName()`: a human-readable descriptive name; **not a unique identifier key**.
- `VirtualMachineDescriptor.provider()`: the provider corresponding to the descriptor.
- `VirtualMachine.attach(String id)`: attempts to attach through the installed providers using the identifier string.
- `VirtualMachine.attach(VirtualMachineDescriptor descriptor)`: attaches through **the provider of the selected descriptor**.
- `vm.getSystemProperties()`: reads the current system properties of the target JVM.
- `vm.detach()`: closes the tool's attach connection to the target JVM.

A typical attach connection is a **local** management mechanism implemented by the JVM/provider and the operating system. `VirtualMachine.attach(...)` **does not automatically invoke `agentmain`** and does not automatically inject code into classes. Requesting to load a Java agent is a separate operation (`vm.loadAgent(...)`), which should only be performed after identity has been verified and with proper operational permissions.

Diagram:

```text
Operator identifies the application to connect to
                  │
                  ▼
Independent info: PID + start time + user + command
                  │
                  ▼
VirtualMachine.list() → select exactly one descriptor
                  │
                  ▼
Recheck process is still alive / unchanged
                  │
                  ▼
VirtualMachine.attach(descriptor)
                  │
                  ▼
Cross-check identity in target (read-only)
                  │
          ┌───────┴────────┐
          │ match          │ mismatch
          ▼                ▼
  operation allowed     refuse to proceed
          │                │
          └───────┬────────┘
                  ▼
            vm.detach()
```

Two important points:

1. **Discovery is not authentication:** a JVM appearing in `VirtualMachine.list()` only proves that the provider could list it at that moment; it does not prove that it is the right service.
2. **Attach does not mean executing an operation:** opening a connection is only one step. The tool itself must control which operations are invoked on that connection.

## 3. `id`, PID, and `displayName`: using each for its proper role

### 3.1. `VirtualMachineDescriptor.id()` is not specified to be a PID in every environment

In standard HotSpot/JDK, `VirtualMachineDescriptor.id()` is usually the OS PID represented as a string. However, the API describes it as an **implementation-dependent identifier**. Another `AttachProvider` may use a different identification scheme.

Therefore:

```java
// Example only for environments where the provider uses PID:
String vmId = Long.toString(targetPid);
```

This snippet is **not a universal rule** for every JVM/provider. If a tool needs to cross-check `ProcessHandle.of(pid)`, it must first have grounds to know that the `id()` of the provider in use maps directly to a PID as seen from the current namespace.

### 3.2. `displayName` only helps humans distinguish targets

A JVM may display `com.example.Server`, `app.jar`, a command string, or just the ID itself depending on how the descriptor was created. Two processes running the same JAR can have the exact same `displayName`. Thus you must never automatically "pick the first entry whose name contains `orders`".

You should check a combination of signals:

| Evidence | Where can it be obtained? | Value and limitations |
| --- | --- | --- |
| **PID or provider ID** | Startup logs, process management tools, `descriptor.id()` | Selects candidates; may be reused or differ across namespaces |
| **Process start time** | `ProcessHandle.Info.startInstant()` or OS tools | Distinguishes a new process from an old one whose PID was reused; info may not be provided |
| **Process owner user** | `ProcessHandle.Info.user()` / OS | Helps confirm the operating principal; does not replace authentication |
| **Executable/command line** | `ProcessHandle.Info.commandLine()` / OS | Distinguishes applications; may be missing, truncated, or identical |
| **Descriptor/provider** | `VirtualMachine.list()` | Confirms the candidate JVM was recognized by the provider at discovery time |
| **Application-emitted marker** | Runtime logs/console; after attach, can compare a system property or management data | Cross-verification; a visible marker is **not a password or tamper-proof proof** |

In real environments, stronger verification sources may be process records from a supervisor/orchestrator, deployment instance IDs, container IDs, and startup metadata. Do not use a single display name or PID as the sole basis.

### 3.3. PID reuse: why is start time needed?

Suppose process A has PID `3180` at 10:00 and exits at 10:05. Afterward, the OS may reassign PID `3180` to process B. If a tool keeps the old ID in a cache, `attach("3180")` at 10:10 could connect to B.

Comparing `(PID, startInstant)` helps detect this change in environments where the OS provides an accurate start time. You must **recheck right before attaching and after attaching**, because reading the list and connecting are two separate operations and do not form an atomic transaction.

## 4. Workflow for attaching with a verified identifier

**Step 1 — Identify the authorized target.** The operator specifies the exact service name, instance/deployment, and desired environment. For the learning example, the target application prints its own PID, start time, and marker at startup.

**Step 2 — Obtain the PID/ID from a trusted source.** Get the PID from the managed process itself or from the logs of the instance to be accessed. If using `jcmd -l` or `VirtualMachine.list()`, treat it as a **candidate list** for further cross-checking.

**Step 3 — Check the process at the OS level.** For PID-based IDs, use `ProcessHandle.of(pid)` to check `isAlive()`, `info().startInstant()`, `info().user()`, and `info().commandLine()` if the OS permits. If required data is unavailable, **do not guess**; use another trusted verification source or abort.

**Step 4 — Match the descriptor.** Find the corresponding ID in `VirtualMachine.list()`. If absent, or if multiple descriptors cannot be distinguished, do not pick arbitrarily. `displayName` is only a supplementary signal.

**Step 5 — Recheck right before attaching.** Ensure the PID is still alive, the start time has not changed, and the user/command still match. If anything differs from the previous check, abort and re-identify from the beginning.

**Step 6 — Call `VirtualMachine.attach(descriptor)`.** Once you have the descriptor for the right provider, this overload preserves the provider choice instead of probing across providers by ID string.

**Step 7 — Verify after attaching before any sensitive operation.** Recheck the OS identity and, if the application has an identification mechanism, compare a marker/property of the exact target. If it does not match, refuse the next step.

**Step 8 — Call `detach()` in `finally`.** Even if a check or operation throws an exception, still attempt to close the connection. `detach()` does not terminate the target JVM; if an agent was loaded earlier, detaching also **does not automatically unload the agent**.

This sequence reduces operational mistakes, but it does not turn a PID or marker into a cryptographic authentication mechanism. Attach permission control is still governed by the OS/JVM and deployment policies.

## 5. Prerequisites before running the experiment

The experiment below uses **JDK 17 or later**, with a standard HotSpot/OpenJDK distribution that includes the `jdk.attach` module. Two separate Java programs run on **the same machine and under the same OS user**. Ensure:

- `java -version` and `javac -version` point to a suitable JDK; do not use a custom runtime image that stripped `jdk.attach`.
- The target JVM allows attach. For example, run **without** `-XX:+DisableAttachMechanism`.
- You have permission to access the process and the required `ProcessHandle.Info` metadata. Some OSes, containers, or permission policies may hide `startInstant`, user, or command line.
- Use the exact PID **printed by the target JVM itself**. In the experiment, the HotSpot provider maps the ID to the PID in the same PID namespace.
- Do not attempt to self-attach to the tool's own JVM; the verifier and target programs run in two different processes.
- A process can exit at any time. Do not treat a pre-attach check result as a permanent guarantee.

This is an experiment about **identity and connection**. The verifier program only reads the `attach.demo.id` property after attaching; it does not load an agent, does not require enabling JMX, and does not modify classes.

## 6. Java 17+ example: creating a target JVM with an identifying marker

Create the file **`AttachTarget.java`**:

```java
import java.time.Instant;

public final class AttachTarget {
    public static void main(String[] args) throws InterruptedException {
        String marker = System.getProperty("attach.demo.id");
        if (marker == null || marker.isBlank()) {
            throw new IllegalStateException(
                    "Missing -Dattach.demo.id system property");
        }

        ProcessHandle self = ProcessHandle.current();
        Instant started = self.info().startInstant()
                .orElseThrow(() -> new IllegalStateException(
                        "OS process start time is unavailable"));

        System.out.println("PID=" + self.pid());
        System.out.println("START=" + started);
        System.out.println("MARKER=" + marker);
        System.out.flush();

        // Keep the process running so the verifier can connect from another terminal.
        while (true) {
            Thread.sleep(1_000);
        }
    }
}
```

Things to observe:

- `ProcessHandle.current().pid()` returns the PID **of the target JVM itself**, not the verifier's PID.
- `startInstant()` returns the time the OS recorded the process creation, if that information is available.
- `-Dattach.demo.id=...` sets a Java system property before `main`. The example uses an easily recognizable marker, **not a secret**.
- `while (true)` merely keeps the JVM alive long enough to practice the steps; stop it with `Ctrl+C` when finished.

## 7. Java 17+ example: verifier checks the ID then attaches

Create the file **`VerifiedAttach.java`**:

```java
import com.sun.tools.attach.VirtualMachine;
import com.sun.tools.attach.VirtualMachineDescriptor;
import java.time.Instant;
import java.util.List;
import java.util.Properties;

public final class VerifiedAttach {

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                    "Usage: VerifiedAttach <PID> <START> <MARKER>");
            System.exit(2);
        }

        String suppliedId = args[0];
        long pid = Long.parseLong(suppliedId);
        Instant expectedStart = Instant.parse(args[1]);
        String expectedMarker = args[2];

        if (pid <= 0 || !suppliedId.equals(Long.toString(pid))
                || expectedMarker.isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid PID or marker");
        }

        // Check OS evidence before selecting the JVM.
        verifyProcess(pid, expectedStart);

        List<VirtualMachineDescriptor> matches = VirtualMachine.list()
                .stream()
                .filter(d -> suppliedId.equals(d.id()))
                .toList();

        if (matches.size() != 1) {
            throw new IllegalStateException(
                    "Expected exactly one attach descriptor for PID");
        }

        VirtualMachineDescriptor descriptor = matches.get(0);
        if (!descriptor.displayName().contains("AttachTarget")) {
            throw new IllegalStateException(
                    "Unexpected JVM display name");
        }

        // Recheck right before the attach operation.
        verifyProcess(pid, expectedStart);

        VirtualMachine vm = VirtualMachine.attach(descriptor);
        try {
            // Do not call loadAgent or any JVM-modifying operation before verification.
            verifyProcess(pid, expectedStart);
            Properties properties = vm.getSystemProperties();

            if (!expectedMarker.equals(
                    properties.getProperty("attach.demo.id"))) {
                throw new IllegalStateException(
                        "Target marker does not match");
            }

            // One final check to detect PID/process changes.
            verifyProcess(pid, expectedStart);

            System.out.println("IDENTITY=VERIFIED");
            System.out.println("ATTACH=READ_ONLY_SUCCESS");
        } finally {
            vm.detach();
        }
    }

    private static void verifyProcess(long pid, Instant expectedStart) {
        ProcessHandle process = ProcessHandle.of(pid)
                .orElseThrow(() -> new IllegalStateException(
                        "Target PID no longer exists"));

        if (!process.isAlive()) {
            throw new IllegalStateException("Target is not alive");
        }

        ProcessHandle.Info info = process.info();

        Instant currentStart = info.startInstant()
                .orElseThrow(() -> new IllegalStateException(
                        "Cannot verify target start time"));
        if (!currentStart.equals(expectedStart)) {
            throw new IllegalStateException(
                    "PID was reused or start time differs");
        }

        String targetUser = info.user()
                .orElseThrow(() -> new IllegalStateException(
                        "Cannot verify target OS user"));
        String ownUser = ProcessHandle.current().info().user()
                .orElseThrow(() -> new IllegalStateException(
                        "Cannot verify verifier OS user"));
        if (!targetUser.equals(ownUser)) {
            throw new IllegalStateException(
                    "Target is owned by a different OS user");
        }

        String commandLine = info.commandLine()
                .orElseThrow(() -> new IllegalStateException(
                        "Cannot verify target command line"));
        if (!commandLine.contains("AttachTarget")) {
            throw new IllegalStateException(
                    "Target command line does not match");
        }
    }
}
```

### Why is this code intentionally "strict"?

- `args[0]` must be a canonical decimal PID string in the demo environment, rejecting things like `000123` as a way of guessing the ID.
- `Instant.parse(args[1])` uses **the exact timestamp** printed by the target, rather than guessing from when the program was launched.
- `verifyProcess(...)` fails immediately if critical metadata is missing, instead of treating `Optional.empty()` as "probably fine".
- `matches.size() != 1` rejects ambiguous or non-unique descriptors. `VirtualMachine.list()` can change over time.
- `displayName.contains("AttachTarget")` is an extra check tailored to **the example's launch command**. In real applications, display names should not be treated as a trusted identity.
- `VirtualMachine.attach(descriptor)` selects the exact provider belonging to the matched descriptor. The `attach(String)` overload is also valid when the ID is known for the right provider/environment, but it requires the same verification policy.
- Reading the marker happens **after attaching but before any operation that could affect the JVM**. In the demo, it only proves the target has the expected property; it must not be used as a security authorization mechanism.
- `finally` ensures `vm.detach()` is called if the attach connection succeeded, even if the property does not match or the read operation fails.

Note: the code compiles with Java 17+, but a successful attach also depends on the OS, JDK, process permissions, attach provider, and `ProcessHandle.Info` data. **Refusing to proceed when evidence is insufficient** is intentional behavior.

## 8. Compiling and running in two terminals

In the directory containing `AttachTarget.java` and `VerifiedAttach.java`, open terminal 1 and compile:

```powershell
javac --add-modules jdk.attach -encoding UTF-8 AttachTarget.java VerifiedAttach.java
```

This command tells the compiler to resolve `jdk.attach`, which provides the `VirtualMachine`/`VirtualMachineDescriptor` classes.

**Terminal 1 — run the target JVM:**

```powershell
java -Dattach.demo.id=lab-alpha AttachTarget
```

The target prints three lines of the form:

```text
PID=...       (actual PID assigned by the OS)
START=...     (actual Instant in ISO-8601 format)
MARKER=lab-alpha
```

The first two lines are **dynamic values**, so there is no fixed stdout across runs. Copy the exact values after `PID=` and `START=`. Keep terminal 1 running.

**Terminal 2 — enter the two values you received and perform the attach:**

```powershell
$verifiedPid = Read-Host "PID printed by AttachTarget"
$verifiedStart = Read-Host "START printed by AttachTarget"
java --add-modules jdk.attach VerifiedAttach $verifiedPid $verifiedStart lab-alpha
```

**Verifier stdout when all checks succeed:**

```text
IDENTITY=VERIFIED
ATTACH=READ_ONLY_SUCCESS
```

These lines appear only after the OS identity, descriptor, target property, and final recheck all succeed.

When finished, press `Ctrl+C` in terminal 1 to stop `AttachTarget`. `vm.detach()` itself only closes the management connection channel; it does not terminate the target JVM.

### If using Bash on Linux/macOS

The Java compilation and startup steps remain the same. In the verifier terminal, you can enter:

```bash
read -r -p "PID printed by AttachTarget: " verified_pid
read -r -p "START printed by AttachTarget: " verified_start
java --add-modules jdk.attach VerifiedAttach \
    "$verified_pid" "$verified_start" lab-alpha
```

On both operating systems, you must run the target and verifier in compatible contexts regarding PID namespace and attach permissions.

## 9. Reading the program flow: pre-attach and post-attach verification

### Before attach

```java
verifyProcess(pid, expectedStart);
```

This is an **OS process** check using `ProcessHandle`. It is not an Attach API call and does not require connecting to the target JVM. It compares the recorded information from the desired instance against the existing process.

Next:

```java
List<VirtualMachineDescriptor> matches = VirtualMachine.list()
        .stream()
        .filter(d -> suppliedId.equals(d.id()))
        .toList();
```

This is a **JVM/provider** check. A PID may exist without being an attachable JVM; `ProcessHandle` does not prove it supports the Attach API. Conversely, a valid descriptor does not yet prove it is the authorized instance.

Then:

```java
VirtualMachine vm = VirtualMachine.attach(descriptor);
```

Only at this point does the tool ask the provider to connect. Checking via the OS and provider in the previous two steps reduces the chance of picking the wrong JVM; it does not completely eliminate the possibility of the target changing between steps.

### After attach

```java
Properties props = vm.getSystemProperties();
String marker = props.getProperty("attach.demo.id");
```

This operation **reads current information from the target**, not `System.getProperties()` of the verifier. Setting a marker on the target lets us compare it against a known value from an external source.

Only when the marker matches and the process identity remains stable does the verifier print `IDENTITY=VERIFIED`. In a real tool, this is the point where you can decide **whether to proceed with a separate authorized operation**. You should separate verification from execution to avoid targeting the wrong JVM or mixing privileges.

### Why check multiple times?

Imagine the target exits between two operations:

```text
10:00:00.000  read PID 3180, start=T1
10:00:00.100  JVM A exits
10:00:00.200  JVM B is assigned PID 3180 by OS, start=T2
10:00:00.300  attach using string "3180"
```

Without rechecking, the operation could target B. Comparing `startInstant` detects that T2 differs from T1. After attaching, reading the marker adds another layer of verification. However, **there is no atomic transaction between the OS process inspection API and the Attach API**; if higher assurance is required, you must use the process management system's identification/authorization mechanisms and design operations safely for the environment.

## 10. How to choose between `list()`, `attach(String)`, and `attach(descriptor)`?

| Approach | Strengths | What must be checked |
| --- | --- | --- |
| `VirtualMachine.list()` | Discovers candidates and provider/ID; useful for interactive tools | The list may be incomplete and change over time; name and ID alone may not be sufficient verification |
| `VirtualMachine.attach(id)` | Convenient when the provider-specific identifier is already verified | With multiple providers, the API tries providers sequentially; you must know which environment the identifier applies to |
| `VirtualMachine.attach(descriptor)` | Binds to the exact provider that created the descriptor | The descriptor is still a snapshot; the target may have exited, been replaced, or refused attach |

In the demo, the descriptor was selected from `list()` using an OS-verified ID, so using the descriptor overload is easy to reason about. When running in a system where the provider does not use PIDs, you cannot reuse `Long.parseLong(id)`/`ProcessHandle.of(pid)` as-is; you need a verification model suited to that provider.

You should also never construct a `VirtualMachineDescriptor` with a guessed provider to "bypass" not finding the target. Failing to find or verify the target is a result that must be reported clearly.

## 11. When attach fails: reading the cause accurately

| Symptom | Possible cause | Verification direction |
| --- | --- | --- |
| `VirtualMachine.list()` does not show the PID | JVM is not listed by the provider, different namespace, permissions, or process exited | Confirm PID, OS user, namespace, and that target is still running; do not pick another JVM |
| `AttachNotSupportedException` | Provider unsupported, wrong ID, target exited, or attach disabled | Check JVM/provider, target, and JVM flags |
| `IOException` during attach | Communication channel error, file/socket permissions, unresponsive target, platform error | Read the full message/cause, check target logs and OS permissions |
| `SecurityException` | Runtime/provider permission policy blocks the operation | Verify granted permissions; do not auto-escalate privileges |
| `startInstant()`/`user()`/`commandLine()` empty | OS does not provide metadata or insufficient permissions to view it | Stop the sample workflow; find an appropriate independent identification source |
| `PID was reused or start time differs` | Wrong PID or OS reused it | Re-collect info from the right instance; do not retry with the old PID |
| `Unexpected JVM display name` | Not the demo target class or provider formats it differently | Re-check launch command and descriptor; do not arbitrarily skip the check |
| `Target marker does not match` | Connected to a different JVM, wrong run, or marker changed | Detach and verify the new instance before continuing |
| `NoClassDefFoundError` / missing module | JDK/runtime image lacks `jdk.attach` or incorrect module configuration | Check the JDK distribution and `--add-modules jdk.attach` |
| JVM in a different PID namespace | PID seen from host differs from PID seen inside container | Perform attach from the appropriate context, aligning namespace and identifier |

With HotSpot, depending on JVM configuration, the `-XX:+DisableAttachMechanism` flag may be used to disable the attach mechanism. Do not work around errors by disabling identity checks or trying to attach to another JVM just because it "looks similar".

### Distinguishing attach errors from dynamic agent loading warnings

Starting in JDK 21 (JEP 451), **loading a Java agent/JVMTI agent into a running JVM** has dedicated warnings/policies in preparation for restricting dynamic loading. Calling `VirtualMachine.attach(...)` and **only** calling `getSystemProperties()` as in this lab is **not** an agent-loading operation. Avoid assuming that a `loadAgent`-related warning means all attach operations fail, or that merely adding a VM flag grants authorization over the target.

If a future task requires `loadAgent`, you must check the JDK version in use, the target's allowlist/opt-in mechanism, and operational permissions. That topic is a separate step after identity verification.

## 12. Safety and reliability rules when building real tools

1. **Never accept an unverified PID and immediately attach.** Start from the exact instance record, and do not blindly pick the first element in `VirtualMachine.list()`.
2. **Never treat displayName, main class, or JAR name as unique.** Multiple environments/services can use the same class.
3. **Never treat the demo marker as a secret or authentication.** Anyone with permission to observe the command line or modify system properties can read/alter the marker; use an independent authorization mechanism if the task is sensitive.
4. **Never log all of `getSystemProperties()`.** Target properties may contain configuration details or sensitive data. Read and process only the required fields.
5. **Never trust cached info for too long.** PIDs and descriptors are snapshots at the time of reading; recheck before performing operations.
6. **Never auto-escalate privileges to attach.** Use only the process permissions already granted, under the right user and environment.
7. **Set timeouts and handle errors clearly.** Attach can be slow, and the target may be busy or stopped; an orchestration tool should have a control-plane timeout and report the cause.
8. **Always have a detach strategy.** Use `finally` appropriately when `attach()` returns successfully; if `detach()` throws an `IOException`, report the error as well and do not pretend the session closed cleanly.
9. **Never confuse attach with a permanent state.** The connection is a control session; the JVM keeps running after detach, and prior changes (if any) are not automatically reverted.
10. **Test in real deployment environments.** HotSpot, OpenJ9, containers, OSes, and JDK versions may differ in providers, permissions, process metadata, and agent mechanisms.

## 13. Self-practice scenarios

### Scenario A — two JVMs running the same main class

Both A and B are `AttachTarget`, differing only in PID, `START`, and marker. A tool filtering `displayName.contains("AttachTarget")` will find both.

**Approach:** use the PID explicitly published by the exact target, cross-check start time and OS user, select the descriptor by ID, and verify the marker of that specific run. If evidence is missing, stop.

### Scenario B — PID was right yesterday but belongs to a different process today

The old record has `(PID=3180, START=T1)`, while the new process has `(PID=3180, START=T2)`.

**Result:** `verifyProcess` reports a start time mismatch. Do not call attach with the old ID. Obtain the record for the new instance and confirm it is actually the intended target.

### Scenario C — attached, but marker is wrong

The connection is established, and `getSystemProperties()` returns a non-matching marker.

**Result:** the verifier throws an exception, and `finally` calls `detach`. No target-modifying operation is invoked. This is why post-attach checks must come **before** impactful steps.

### Scenario D — `list()` returns no descriptor while the process is alive

`ProcessHandle.of(pid).isAlive()` is true, but there is no corresponding descriptor.

**Conclusion:** A living process does not automatically mean an attachable JVM within the provider's scope. You must verify configuration, permissions, and namespace; do not swap IDs or pick a different JVM.

### Scenario E — only PID is available, no start time

`ProcessHandle.Info.startInstant()` is empty due to OS policy.

**Conclusion:** The sample workflow refuses to continue. In a real tool, you need another trusted identity source, such as a supervisor record with launch timestamp/instance ID, or explicitly accept a different assurance level per defined policy; never turn "missing data" into "verified".

## 14. Comprehension check questions

**1. Is `VirtualMachineDescriptor.id()` always a PID?**  
No. The API only guarantees it is a provider identifier; on many JVMs/OSes it is commonly the PID.

**2. Can you attach using only `displayName`?**  
No API guarantees uniqueness of `displayName`. It is meant for display, so you must cross-check the ID and other target metadata.

**3. Why record `startInstant` in addition to the PID?**  
Because the OS can reuse PIDs, start time helps detect a matching PID belonging to a different process lifecycle.

**4. Does `VirtualMachine.attach(...)` immediately run `agentmain` or inject bytecode?**  
No. It is a connection-establishment operation. Only when an appropriate agent-loading operation is performed is the agent asked to run according to its mechanism.

**5. After `vm.getSystemProperties()`, can you print every property for debugging?**  
You should not. Properties may contain sensitive data; inspect only the required keys.

**6. Does `vm.detach()` stop the JVM or unload a loaded agent?**  
No. It only disconnects the tool's attach session.

**7. If the marker matches, can that be treated as security authentication?**  
No. The marker is a cross-check signal in the lab, not a credential, and does not replace system access-control mechanisms.

**8. Why use `attach(descriptor)` instead of `attach(id)` in the example?**  
The descriptor holds a reference to the provider that listed the candidate JVM; this stays tied to the exact provider/ID pair just verified. You still need to check lifecycle and target because the descriptor can become stale.

## 15. Official references

- [JDK 21 — `VirtualMachine`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): `list`, `attach`, `getSystemProperties`, `detach`, and agent-loading operations.
- [JDK 21 — `VirtualMachineDescriptor`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachineDescriptor.html): `id`, `displayName`, `provider`, and the implementation-dependent nature of identifiers.
- [JDK 21 — `ProcessHandle.Info`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.Info.html): `startInstant`, `user`, `commandLine`, and the optionality of process metadata.
- [OpenJDK — JEP 451](https://openjdk.org/jeps/451): warnings/policies on dynamic agent loading, distinct from read-only attach connections.

**Key takeaway:** An "attachable" JVM is not necessarily **the right JVM**. Use `VirtualMachine.attach(...)` only after matching the ID against evidence of the exact instance, recheck before and after connecting, perform only authorized operations, and always `detach()` when done.
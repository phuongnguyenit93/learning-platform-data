# OS Permissions, Containers, Self-Attach, and Vendor Support When Attaching to the JVM

**Context:** Java Advance → instrumentation → **Attaching to the JVM**. A tool such as `jcmd`, `jstack`, or a program using `com.sun.tools.attach.VirtualMachine.attach(...)` may fail to connect to a running JVM, even when the PID exists. The cause usually belongs to **OS permissions, PID/container namespaces, the JVM attach mechanism, agent loading policy, or vendor implementation**.

This lesson helps distinguish permission layers, test self-attach and external attach yourself, understand Docker/Kubernetes conditions, recognize differences among HotSpot, Eclipse OpenJ9, and GraalVM Native Image, and diagnose issues step by step. Examples use Java 17+ and primarily explain **HotSpot** behavior; `-XX` flags and connection details must be cross-checked against the documentation of the actual VM.

## 1. What Is Attach? Why Are There Multiple Layers of Conditions?

```text
Client tool (JDK / Attach API)                Running JVM (target)
  │                                                │
  ├── find the right PID ─────────────────────────►│
  ├── check provider & runtime ───────────────────►│
  ├── OS: user/group, signal, filesystem ─────────►│
  ├── container: PID/mount namespace, /proc ──────►│
  ├── handshake with attach listener ─────────────►│
  │                                                │
  ├── diagnostic command / getSystemProperties ───►│  [does not load agent]
  └── loadAgent(JAR) ─────────────────────────────►│  [adds agent policy]
```

**Three distinct operations:**

| Operation | Example | Additional requirements |
| --- | --- | --- |
| View process via OS | `ps`, `id`, `/proc/<pid>` (Linux) | OS permissions and namespace; not yet connected to the JVM |
| Attach and retrieve information | `jcmd PID VM.version`, `VirtualMachine.attach` + `getSystemProperties` | Compatible provider, OS permissions, attach listener/mount |
| Attach then dynamically load an agent | `VirtualMachine.loadAgent("agent.jar")` | In addition to attach, requires dynamic agent policy, `Agent-Class` manifest, `agentmain`, and a valid JAR |

**`jcmd PID VM.version` succeeding does not prove `loadAgent` will succeed.** Conversely, a `loadAgent` failure does not necessarily mean the OS forbids attach.

A Java agent passed at **JVM startup** via `-javaagent:path/to/agent.jar` is a different path: the JVM invokes `premain`. When an agent is loaded into a **running** JVM, the JVM invokes `agentmain`. These two mechanisms have different conditions and policies.

## 2. Operating System Permissions

### 2.1. Linux/Unix: Effective UID/GID and Process Permissions

According to Oracle `jcmd` documentation, the diagnostic tool must run on the **same machine** as the target JVM and with the **same effective user and group identifiers** used to run that JVM. On service systems, the user opening a terminal is very likely **different** from the account running the application.

Read-only check on Linux, replacing the example PID with the real value:

```bash
id
ps -o pid,ppid,user,uid,euid,group,gid,egid,args -p 12345
jcmd 12345 VM.version
```

- `UID` and `EUID` are the real user ID and effective user ID; `GID`/`EGID` are the same for the group. Verify **numeric identity** rather than relying only on the account name.
- PIDs can be reused when a service/container restarts. Verify that the process is alive and is actually the JVM you intend to inspect.
- Permission to send signals, access `/proc/<PID>`, permissions on the temporary directory, and the IPC mechanism can affect attach on HotSpot/Linux.
- SELinux, AppArmor, seccomp, namespaces, ACLs, or process protection policies may block the operation even when both processes can see each other.
- Running as `root` does not automatically guarantee success: socket permission checks, namespaces, or hardening can still prevent connection. Elevated privileges should only be used when operational policy permits.

In HotSpot Unix/Linux, while debugging you may encounter files/sockets like `.attach_pid<PID>` or `.java_pid<PID>`. These are **implementation details** of HotSpot, not a Java SE standard applicable to every VM. With OpenJ9, the default attach directory is `.com_ibm_tools_attach` and the IPC mechanism is different.

**Avoid quick fixes by opening global permissions:** do not arbitrarily run `chmod 777`, delete attach sockets currently in use, change the owner of `/tmp`, disable SELinux/AppArmor, or run a container with `--privileged` just to test. Those changes can break other processes or reduce the security of the entire host.

### 2.2. Windows and macOS

On **Windows**, process/token permissions, ACLs, sessions, integrity levels, and system protection software can have an effect; do not use Linux `/proc` or `/tmp` checks. On **macOS**, user permissions, sandboxing, and process protection policies can restrict attach. For both, use the tools bundled with the target's JDK/vendor and interpret errors according to the specific API/OS, without inferring from Linux messages.

## 3. HotSpot: Disabling Attach Is Different from Prohibiting Dynamic Agents

| Flag at **target JVM startup** | Practical meaning |
| --- | --- |
| `-XX:+DisableAttachMechanism` | Disables the mechanism for tools to attach to HotSpot. `jcmd`/Attach API requests typically fail |
| `-XX:-EnableDynamicAgentLoading` | Disallows dynamic agent loading after the JVM has started; **does not mean** all diagnostic commands are disabled |
| `-XX:+EnableDynamicAgentLoading` | Explicitly allows dynamic agents on HotSpot; related to JEP 451 warnings |
| `-Djdk.attach.allowAttachSelf=true` | On the JVM **calling the Attach API**, allows a HotSpot process to attach to its own PID, if other conditions are valid |

Notes:

1. **Right process:** `-XX:+DisableAttachMechanism` and `EnableDynamicAgentLoading` must be checked on the **target**. Passing the flag to the client tool does not override the policy already set on the target.
2. **Right scope:** `allowAttachSelf` only handles the case where client and target are the **same JVM**; it does not grant extra OS privileges or open a path across containers.
3. **Right timing:** many options are read by the JVM at startup; calling `System.setProperty` mid-execution cannot be treated as a way to change the self-attach policy.
4. **Right implementation:** `-XX` flags are VM-specific; do not assume every vendor behaves identically to HotSpot.

### JDK 21+ and JEP 451

Starting in **JDK 21**, JEP 451 causes HotSpot to emit a warning when a **Java/JVMTI agent is dynamically loaded** into a running JVM, in preparation for stricter policies in the future. On JDK releases where dynamic loading is allowed by default, the message is a **warning**, and does not by itself mean attach failed. The `-XX:+EnableDynamicAgentLoading` flag at startup is a way to express explicit intent to allow it and suppress the warning. `-XX:-EnableDynamicAgentLoading` lets you test disallowed behavior. When upgrading the JDK, verify the default of the actual release; do not treat promises about future releases as changes that have already happened.

Example **target** where the owner explicitly allows dynamic agents:

```bash
java -XX:+EnableDynamicAgentLoading -jar service.jar
```

Example protecting the target from agents loaded after startup, while still allowing certain diagnostic commands per VM policy:

```bash
java -XX:-EnableDynamicAgentLoading -jar service.jar
```

None of the flags here replace the requirement for the right user/group, provider, namespace, or valid agent JAR. `-javaagent` at startup and `loadAgent` after startup are two different initialization paths.

## 4. Self-Attach: A JVM Connecting to Itself

**Self-attach** occurs when a program calls `VirtualMachine.attach` with its own PID. **HotSpot since JDK 9** blocks this mechanism by default, even when UID/GID match completely. Common error:

```text
java.io.IOException: Can not attach to current VM
```

On HotSpot, it can be enabled in an environment authorized for testing using a property **at JVM startup**:

```bash
java -Djdk.attach.allowAttachSelf=true ...
```

This property is **not** equivalent to `-XX:+EnableDynamicAgentLoading`. A self-attach that only reads system properties does not need to load an agent. If a library uses self-attach to call `loadAgent`, it will encounter **both** policies.

### 4.1. Java 17+ Program to Test the Attach API

Create the following **`AttachProbe.java`** file. This is a standalone Java program using the `jdk.attach` module, with no external library dependencies:

```java
import com.sun.tools.attach.VirtualMachine;
import java.util.Properties;

public final class AttachProbe {
    private AttachProbe() {}

    public static void main(String[] args) throws Exception {
        String pid = args.length == 0 || "self".equals(args[0])
                ? Long.toString(ProcessHandle.current().pid())
                : args[0];

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            Properties props = vm.getSystemProperties();
            System.out.println("ATTACHED");
            System.out.println("VM_NAME_PRESENT="
                    + (props.getProperty("java.vm.name") != null));
        } finally {
            vm.detach();
        }
    }
}
```

Compile and test self-attach using **JDK 17+ running HotSpot**, in an environment where attach is not prohibited:

```bash
javac --add-modules jdk.attach AttachProbe.java
java --add-modules jdk.attach -Djdk.attach.allowAttachSelf=true AttachProbe self
```

When attaching and reading system properties succeed, the program's stdout is:

```text
ATTACHED
VM_NAME_PRESENT=true
```

If `-Djdk.attach.allowAttachSelf=true` is omitted, HotSpot usually throws `Can not attach to current VM` before printing `ATTACHED`. The error text/stack trace may vary by JDK; do not treat the exact exception message as an API contract.

`getSystemProperties` only reads target configuration and does not load an agent. Running the example above successfully **does not test** dynamic Java agent loading.

### 4.2. External Attach Using a Second JVM

Create the **`TargetApp.java`** file:

```java
public final class TargetApp {
    private TargetApp() {}

    public static void main(String[] args) throws InterruptedException {
        System.out.println("TARGET_PID=" + ProcessHandle.current().pid());
        Thread.sleep(120_000);
    }
}
```

In **Terminal A**:

```bash
javac TargetApp.java
java TargetApp
```

`TargetApp` prints `TARGET_PID=...` with the actual PID, then stays alive for about two minutes. In **Terminal B** on the same machine, running under the appropriate effective user/group, replace `12345` with the PID just printed:

```bash
java --add-modules jdk.attach AttachProbe 12345
jcmd 12345 VM.version
```

If `AttachProbe` attaches successfully, the stdout of **the AttachProbe command alone** is:

```text
ATTACHED
VM_NAME_PRESENT=true
```

The `jcmd` command has version/vendor-dependent output, with no fixed stdout string. **External attach does not require allowAttachSelf** because the caller and target are two different JVMs. However, OS, provider, runtime, and container permissions are still required. You can use `jcmd 12345 help` to see the diagnostic commands actually supported.

Regarding the API, always call `vm.detach()` when finished; `VirtualMachine` is not `AutoCloseable` to use `try`-with-resources by default in this example.

## 5. Containers: PID Namespace and Mount Namespace Are Two Separate Issues

A container changes how tools view PIDs, filesystems, and process permissions:

| Component | Why does it affect attach? |
| --- | --- |
| **PID namespace** | The JVM may be PID `1` inside the container but have a different PID on the host; the PID used by the client must identify the right target in the client's namespace |
| **Mount namespace** | The client may see a different `/tmp` directory from the JVM, making attach files/sockets inaccessible |
| **User namespace** | Numeric UID/GID may be mapped differently; two processes showing the same username does not guarantee the kernel treats them as the same identity |
| **`/proc` visibility** | `/proc/<pid>` hidden, unmounted, or restricted by policy will affect lookup/handshake on some systems |
| **Security profile** | seccomp, SELinux, AppArmor, capabilities, and process/signal policies may deny the operation |
| **Runtime image** | Minimal images often lack `jcmd`, `ps`, a shell, or the `jdk.attach` module |

Oracle `jcmd` documentation emphasizes that `jcmd -l` cannot list JVMs located in separate Docker process namespaces; use `ps`/PID directly. **Not seeing a PID in `jcmd -l` does not mean the process is dead**.

### 5.1. Docker: Test in the Right Container, Right User

If the image has JDK tools and the JVM is actually PID 1, for example:

```bash
docker exec --user 10001:10001 my-java-app jcmd 1 VM.version
```

The command above is **only an example with assumptions**: container `my-java-app` is running, the JVM is PID `1`, the target runs with UID/GID `10001`, and `jcmd` exists. If PID 1 is a shell/init, find the JVM PID inside the container first. Do not guess the UID from the `app` name.

Read-only check inside the container **if a shell and tools are present**:

```bash
id
ps -eo pid,ppid,uid,gid,args
java -version
jcmd -l
```

If the production image is distroless or a custom `jlink` image without `jcmd`, that is **missing client-side tools**, not enough to conclude the target JVM disabled attach. Use a diagnostic solution prepared in the deployment or a debug environment matching the namespace/permissions, instead of altering host-wide permissions.

### 5.2. Kubernetes: Same Pod Does Not Guarantee Visibility

- **`kubectl exec` into the application container itself**: has a chance to see the right PID/mount namespace, though tools may not be packaged and the user must still match.
- **Sidecar**: Pods do not share the process namespace by default; `shareProcessNamespace` only solves part of the PID visibility problem, and **does not automatically share the mount namespace** or permissions.
- **Ephemeral debug container**: target visibility depends on the runtime and `--target`/security context; having the `jcmd` binary does not guarantee permission to access the process.
- **Rootless, read-only filesystem, private `/tmp`**: UID mapping, temporary space, and IPC paths must be examined before concluding the JVM is at fault.

A useful sequence when attaching from a container: confirm the process and PID **in the tool's namespace** → check effective UID/GID → check mount/temp/`/proc` and security policy → check VM vendor/flags → try a small diagnostic command. In some modern HotSpot/Linux setups, tools can access the JVM's temp space via `/proc/<pid>/root/tmp`; do not deduce "must share `/tmp`" or "nothing needs to be shared" as an absolute rule.

Do not delete `.java_pid...` files/sockets, bulk-change `/tmp` permissions, or run containers with `--privileged` to resolve timeouts. Keep the attach path and security policies of other workloads intact.

## 6. What Do Different JVMs and Vendors Support?

The name **Java 17/21/25/26** is not enough to identify the implementation. You need to know the vendor, VM, OS, runtime image, available modules, and tool compatibility.

| Implementation | Capabilities and limitations |
| --- | --- |
| **Oracle JDK / OpenJDK using HotSpot** | Supports `jdk.attach` and `jcmd` when the JDK build includes those components; constrained by OS permissions, HotSpot flags, and runtime image |
| **HotSpot-based distributions** such as Temurin, Corretto, or other HotSpot builds | Usually use the HotSpot mechanism, but you must verify the flags, tools, version, and packaging of the actual build |
| **Eclipse OpenJ9** | Has its own Attach API, equivalent at the API level, but according to documentation only connects from **OpenJ9 to OpenJ9**—an OpenJ9 provider cannot attach to HotSpot; has its own flags and IPC mechanism |
| **GraalVM running in JVM mode** | When running `java` on the HotSpot-based JVM, many JDK/HotSpot mechanisms apply; verify it is running on the JVM and not Native Image |
| **GraalVM Native Image** | Can support **some** diagnostic commands via `jcmd` when built with `--enable-monitoring=jcmd`; not equivalent to the full Attach API or dynamic Java agent loading |
| **Custom `jlink` runtime / minimal image** | May not include `jdk.attach` or the `jcmd` binary; missing tools/modules does not prove the entire VM lacks attach support |

**Eclipse OpenJ9:** project documentation notes `-Dcom.ibm.tools.attach.enable=yes|no` to enable/disable the Attach API. Enabled by default on Linux/macOS/Windows/AIX, **except z/OS**, which has a different default and OMVS restrictions. OpenJ9 uses `.com_ibm_tools_attach` as the default IPC directory, with its own `com.ibm.tools.attach.directory` option and permission rules. Therefore, do not apply HotSpot socket mechanics to OpenJ9; drivers/providers are not cross-compatible.

**GraalVM Native Image:** official Oracle GraalVM for JDK 25 documentation describes the build option:

```bash
native-image --enable-monitoring=jcmd YourApplication
```

This is a **build configuration command**, only runnable when you already have the input application and the appropriate Native Image toolchain. Diagnostic commands on Native Image are a specific supported subset; the documentation also notes platform limitations, including that this feature is not available on Windows in the documented version. `jcmd PID help` returning output **does not prove** JVM instrumentation, `agentmain`, or `VirtualMachine.loadAgent` applies to Native Image.

**Matching tool version:** Oracle notes that running diagnostic tools from one JDK version against a VM of another version is **unsupported**. Prefer the same major version, ideally the same vendor/distribution, even though some commands may still work across versions.

### 6.1. Identifying the Actual Runtime

On the client machine:

```bash
java -version
javac -version
jcmd -h
java --list-modules
```

Inside a Java method running on the target, you can print these properties (this is only a **fragment**, not a standalone class):

```java
System.out.println(System.getProperty("java.vendor"));
System.out.println(System.getProperty("java.vm.name"));
System.out.println(System.getProperty("java.vm.version"));
System.out.println(System.getProperty("java.runtime.version"));
```

`java.vendor` is not identical to `java.vm.name`: one is the distribution vendor, the other is the VM implementation. `--add-modules jdk.attach` only requests **resolving an available module**; it cannot add a module to an image from which it was stripped. If the target is attachable, `jcmd PID VM.version`, `VM.command_line`, and `help` assist in cross-checking, though the actual output may depend on the VM.

## 7. Being Able to Attach Still Might Not Allow Loading an Agent

For Java instrumentation using a dynamic agent, check additionally:

1. The JAR has `META-INF/MANIFEST.MF` declaring `Agent-Class: com.example.Agent`.
2. The agent declares `public static void agentmain(String args, Instrumentation inst)` or the single-parameter variant defined by the specification.
3. The target allows dynamic loading per flags/release; not blocked by `-XX:-EnableDynamicAgentLoading`.
4. The JAR path must be usable from the target's execution context; watch out for mount namespaces, packages, and access permissions.
5. Class file version, dependencies, class loader, and `redefineClasses`/`retransformClasses` requirements are compatible with the VM.

API illustration **placed inside a Java client that already has a `targetPid` variable**, not a standalone program:

```java
VirtualMachine vm = VirtualMachine.attach(targetPid);
try {
    vm.loadAgent("/opt/agents/monitor-agent.jar", "mode=sample");
} finally {
    vm.detach();
}
```

`AttachNotSupportedException` or `IOException` typically appears when connection fails; `AgentLoadException`/`AgentInitializationException` can occur during agent loading/initialization after attach. An agent error does not automatically prove an OS error. If only read-only diagnostics are needed, use appropriate commands without loading an agent.

## 8. Diagnosing by Symptom

| Symptom | Possible cause | How to distinguish |
| --- | --- | --- |
| `jcmd: command not found` | Missing executable / PATH / minimal image | Check tool image, `JAVA_HOME`, JDK modules |
| `jcmd -l` does not show the JVM | Different PID namespace, not permitted to list | Identify PID via `ps` in the appropriate namespace and try the PID directly |
| `Operation not permitted` / `Permission denied` | UID/GID or OS policy | Compare effective identity, check security context/logs |
| `Can not attach to current VM` | Self-attach blocked by HotSpot by default | Confirm caller PID = target PID; use an external process or startup property |
| `AttachNotSupportedException` | Incompatible provider, wrong PID, or VM does not support attach | Compare vendor, version, live process, and attach flags |
| `Unable to open socket file ... doesn't respond` | Timeout, wrong namespace/temp, hung JVM, or attach blocked | Check PID, JVM health, `/proc`, temp, and logs |
| `-XX:+DisableAttachMechanism` on target | JVM does not expose attach mechanism | Check startup configuration; changing it usually requires a restart |
| `Dynamic agent loading is not enabled` | Dynamic agent loading prohibited | Distinguish `jcmd` succeeding from `loadAgent` failing; check target flags |
| `AgentLoadException` / `AgentInitializationException` | Broken JAR/manifest/agentmain/dependencies/path | Inspect manifest, target logs, and stack trace |
| JDK tool version mismatch | Compatibility not guaranteed by vendor | Use matching-version tool and check actual VM |
| HotSpot tool cannot attach to OpenJ9 | Provider/implementation mismatch | Use compatible OpenJ9 instructions and tools |
| Native Image `jcmd` has few commands | Separate diagnostic command set | Check `--enable-monitoring` configuration and exact release docs |

The check sequence should be: **(1) identify JVM/PID → (2) tool/vendor/version → (3) OS UID/GID → (4) PID & mount namespaces → (5) target attach policy → (6) `jcmd VM.version` or `getSystemProperties` → (7) only attempt agent loading if needed**. Record the first failing step, error code, launch flags, and environment; do not lump every error together as "Java lacks permissions."

## 9. Applied Scenarios

**Scenario A — Different UIDs.** A service runs as `svcuser` while a user runs `jcmd` from a terminal as `devuser`. `ps` shows the JVM, yet attach is denied. Run the tool under an authorized effective identity or use a diagnostic path configured by operations, without opening host-wide filesystem permissions.

**Scenario B — JVM in Kubernetes.** A sidecar has `jcmd` but `jcmd -l` is empty. Before changing JVM flags, check whether the two containers share a PID namespace; then verify UID, mount/temp/`/proc`, and policies. "Same Pod" is not sufficient proof.

**Scenario C — Self-attach.** A library in tests attaches to the test JVM's own PID and gets `Can not attach to current VM`. On HotSpot, you can use the `jdk.attach.allowAttachSelf` property at startup, or split into a separate helper JVM. If `loadAgent` is also needed afterward, check JEP 451 and `EnableDynamicAgentLoading` separately.

**Scenario D — Diagnostics work, agent loading fails.** `jcmd PID VM.version` runs normally, but the target started with `-XX:-EnableDynamicAgentLoading`. This is a consistent result: attach diagnostics differ from dynamic agent policy. Do not try to bypass the policy; if the agent is an approved business requirement, plan for `-javaagent` at startup or enable it via official configuration.

**Scenario E — Switching JVMs.** A HotSpot tool cannot attach to an OpenJ9 target. Check providers and tools compatible with OpenJ9, the `com.ibm.tools.attach.enable` flag, and its separate IPC directory. Do not use `allowAttachSelf` to "fix" an incompatibility between two VM implementations.

## 10. Self-Check

1. **`jcmd PID VM.version` succeeds, but `loadAgent` fails. Is there a contradiction?**  
   No. You can have diagnostic permissions while lacking dynamic agent loading permissions/policy.
2. **HotSpot self-attach fails even with identical UIDs. Why?**  
   Since JDK 9, HotSpot blocks attaching to the current VM by default; a startup property or external helper is needed if permitted.
3. **The JVM is PID 1 in a container but PID 48001 on the host. Which PID does a tool inside the container use?**  
   The PID the tool sees in its own namespace, typically 1 under the stated assumptions; you must verify the target.
4. **An image lacks `jcmd`; can you infer that the target does not support the Attach API?**  
   No. A missing client executable is different from the target JVM's capabilities or policies.
5. **Does adding `-XX:+EnableDynamicAgentLoading` to the tool process solve the issue when the target disabled the attach mechanism?**  
   No. You must distinguish which process owns the policy; the client cannot override target flags.
6. **An OpenJ9 tool cannot attach to HotSpot; will enabling `jdk.attach.allowAttachSelf` work?**  
   No. Self-attach is different from incompatible providers across JVM implementations.
7. **Does Native Image supporting `jcmd` automatically support dynamic Java agents?**  
   No. Native Image only has the diagnostic subset explicitly enabled at build time.
8. **A sidecar already sees the Java PID; what else needs to be checked?**  
   Effective UID/GID, mount/IPC/temp, `/proc`, security policy, VM/provider, and agent policy if loading an agent.

## 11. Official Documentation

- Oracle JDK 26 — **`jcmd`**: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html
- Oracle JDK 26 — **`java` launcher and `DisableAttachMechanism`**: https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html
- Oracle JDK 26 — **Attach API / `VirtualMachine`**: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html
- Oracle JDK 26 — **`java.lang.instrument`, `Agent-Class`, `agentmain`, dynamic agent**: https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Oracle JDK 9 — **release notes for self-attach `jdk.attach.allowAttachSelf`**: https://www.oracle.com/java/technologies/javase/9-relnotes.html
- Oracle JDK 21 — **release notes for JEP 451 / agent loading warnings**: https://www.oracle.com/java/technologies/javase/21-relnote-issues.html
- Eclipse OpenJ9 — **Java Attach API, permission, provider, IPC, and flags**: https://eclipse.dev/openj9/docs/attachapi/
- GraalVM for JDK 25 — **`jcmd` with Native Image, scope, and `--enable-monitoring=jcmd`**: https://docs.oracle.com/en/graalvm/jdk/25/docs/reference-manual/native-image/debugging-and-diagnostics/jcmd/

Choose documentation according to the **actual vendor, VM, and release**: the Java API describes the common interface, whereas OS policies, namespaces, handshake mechanisms, and diagnostic capabilities are properties of the environment. Allowing attach should be designed at deployment time to avoid opening additional permissions during incident response.